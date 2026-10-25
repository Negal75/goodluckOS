#!/usr/bin/env python3
"""
install-gaminja.py - goodluckOS installer for the GamiJa R36S stock card.

Measured boot flow of the GamiJa stock firmware (docs/r36s-stock-layout.md):

    boot_normal = fatload sunxi_flash boot 40007fc0 uImage;
                  fatload sunxi_flash boot 48000000 uInitrd;
                  bootm 40007fc0 48000000

The stock u-boot loads the kernel from a FILE on the FAT partition labelled
`boot` (p3), driven by variables in the raw env partition labelled `env`
(p2). There is NO fixed kernel sector. So installing goodluckOS means:

  1. (gate)  verify the card's script.bin against the known GamiJa hash
  2. (safety) extract the stock p3/uImage + p3/uInitrd to a backup dir
  3. (swap)  replace p3/uImage with the goodluckOS uImage (appended-DTB
             kernel, load 0x40008000), delete p3/uInitrd (not needed for a
             partition-rooted kernel; stock boot flow loads it but ours
             drops the initrd from bootcmd)
  4. (env)   rewrite the env partition with our bootcmd/bootargs
  5. (opt)   write the goodluckOS rootfs image into a partition
             (--rootfs-file, target partition `rootfs` (p5, 1 GiB) or
             `emusystem` (p4, 2.5 GiB) chosen with --rootfs-part)

Use on a COPY of your stock dump first. Never operate on the one-and-only
card copy without a backup.

Examples:
    # inspect a dump (read-only plan):
    ./install-gaminja.py --target stock.img
    # install panel1 kernel + write rootfs into p5, on a copy:
    ./install-gaminja.py --target stock-copy.img \
        --uimage uImage_gaminja_a33_panel1 \
        --rootfs-file goodluck_rootfs.img --write
"""

import argparse
import hashlib
import os
import shutil
import struct
import sys
import zlib

SECTOR = 512

# Measured from the analysed stock dump (docs/r36s-stock-layout.md).
SCRIPT_BIN_OFFSET = 20488192
SCRIPT_BIN_KNOWN_SHA256 = "1b78d3d55823076eaee7bf1bedc419800eee7abe9f834e3401700080371b2193"
SCRIPT_BIN_MAX_LENGTH = 131072

UIMAGE_LOAD = 0x40008000
FATLOAD_TARGET = 0x40007FC0  # env fatloads here; header sits 0x40 below load

DEFAULT_ROOT = "/dev/mmcblk0p5"  # partition labelled `rootfs`


# --------------------------------------------------------------------------
# u-boot env (legacy, crc-prefixed)
# --------------------------------------------------------------------------

def build_env_text(pairs):
    lines = []
    for k, v in pairs.items():
        lines.append(f"{k}={v}")
    return ("\0".join(lines) + "\0").encode("ascii")


def build_env_block(pairs, size):
    data = build_env_text(pairs)
    if len(data) + 4 > size:
        raise ValueError(f"env text too large for {size}-byte partition")
    block = bytearray(size)
    block[4 : 4 + len(data)] = data
    # u-boot crc32 covers the whole data area (text + zero padding)
    struct.pack_into("<I", block, 0, zlib.crc32(block[4:]) & 0xFFFFFFFF)
    return bytes(block)


def verify_env_block(block):
    (crc,) = struct.unpack_from("<I", block, 0)
    return crc == (zlib.crc32(block[4:]) & 0xFFFFFFFF)


def parse_env_block(block):
    text = block[4:].split(b"\0\0")[0].decode("ascii", "replace")
    return [line for line in text.split("\0") if line]


# --------------------------------------------------------------------------
# minimal FAT12/FAT16 reader/writer (enough for the p3 `boot` partition)
# --------------------------------------------------------------------------

class FatVolume:
    """Handles the p3 `boot` FAT volume: FAT12 (measured: 2041 clusters)
    or FAT16, root-dir files only."""

    def __init__(self, fileobj, part_off, part_sectors=None):
        self.f = fileobj
        self.off = part_off
        bs = self._read(self.off, 512)
        (self.bytes_per_sector,) = struct.unpack_from("<H", bs, 0x0B)
        (self.sec_per_cluster,) = struct.unpack_from("<B", bs, 0x0D)
        (self.reserved,) = struct.unpack_from("<H", bs, 0x0E)
        self.nfats = bs[0x10]
        (self.root_entries,) = struct.unpack_from("<H", bs, 0x11)
        (total16,) = struct.unpack_from("<H", bs, 0x13)
        (self.fat_sectors,) = struct.unpack_from("<H", bs, 0x16)
        (total32,) = struct.unpack_from("<I", bs, 0x20)
        self.total_sectors = total16 or total32
        if self.bytes_per_sector != SECTOR:
            raise ValueError(f"unexpected bytes/sector {self.bytes_per_sector}")
        if part_sectors is not None:
            # stock mkfs.fat writes BPBs larger than the partition; clamp
            self.total_sectors = min(self.total_sectors, part_sectors)
        self.cluster_bytes = self.sec_per_cluster * SECTOR
        self.fat_off = self.off + self.reserved * SECTOR
        self.root_off = self.fat_off + self.nfats * self.fat_sectors * SECTOR
        self.root_bytes = self.root_entries * 32
        self.data_off = self.root_off + self.root_bytes
        data_sectors = self.total_sectors - (self.data_off - self.off) // SECTOR
        self.nclusters = data_sectors // self.sec_per_cluster
        if self.nclusters < 4086:
            self.fat_type = 12
        elif self.nclusters <= 65524:
            self.fat_type = 16
        else:
            raise ValueError("FAT32 not supported here")

    def _read(self, off, n):
        self.f.seek(off)
        return self.f.read(n)

    def _write(self, off, data):
        self.f.seek(off)
        self.f.write(data)

    # -- FAT table ---------------------------------------------------------
    def read_fat(self):
        return bytearray(self._read(self.fat_off, self.fat_sectors * SECTOR))

    def fat_get(self, fat, n):
        if self.fat_type == 12:
            o = n + (n >> 1)
            v = fat[o] | (fat[o + 1] << 8)
            return (v >> 4) & 0xFFF if n & 1 else v & 0xFFF
        return struct.unpack_from("<H", fat, n * 2)[0]

    def fat_set(self, fat, n, value):
        if self.fat_type == 12:
            o = n + (n >> 1)
            if n & 1:
                fat[o] = (fat[o] & 0x0F) | ((value & 0xF) << 4)
                fat[o + 1] = (value >> 4) & 0xFF
            else:
                fat[o] = value & 0xFF
                fat[o + 1] = (fat[o + 1] & 0xF0) | ((value >> 8) & 0xF)
        else:
            struct.pack_into("<H", fat, n * 2, value)

    def eoc(self):
        return 0xFFF if self.fat_type == 12 else 0xFFFF

    def write_fats(self, fat):
        for i in range(self.nfats):
            self._write(self.fat_off + i * self.fat_sectors * SECTOR, fat)

    def cluster_off(self, n):
        return self.data_off + (n - 2) * self.cluster_bytes

    # -- directory ---------------------------------------------------------
    def read_dir(self):
        return self._read(self.root_off, self.root_bytes)

    def write_dir(self, dirbuf):
        self._write(self.root_off, bytes(dirbuf))

    def find_entry(self, dirbuf, name83):
        for i in range(0, len(dirbuf), 32):
            e = dirbuf[i : i + 32]
            if e[0] == 0x00 or e[0] == 0xE5 or e[11] == 0x0F:
                continue
            short = (e[0:8] + e[8:11]).decode("ascii", "replace").rstrip()
            if short.upper() == name83.upper():
                return i, e
        return None, None

    def follow_chain(self, fat, start):
        chain = []
        n = start
        eoc_min = 0xFF8 if self.fat_type == 12 else 0xFFF8
        while 2 <= n < eoc_min:
            chain.append(n)
            n = self.fat_get(fat, n)
            if n in chain:
                raise ValueError("FAT loop")
            if len(chain) > self.nclusters:
                raise ValueError("FAT chain too long")
        return chain

    def read_chain(self, fat, start, size):
        out = bytearray()
        for n in self.follow_chain(fat, start):
            out += self._read(self.cluster_off(n), self.cluster_bytes)
        return bytes(out[:size])

    def free_chain(self, fat, start):
        for n in self.follow_chain(fat, start):
            self.fat_set(fat, n, 0)

    def count_free(self, fat):
        free = 0
        for n in range(2, 2 + self.nclusters):
            if self.fat_get(fat, n) == 0:
                free += 1
        return free

    def allocate(self, fat, nclusters):
        chain = []
        for n in range(2, 2 + self.nclusters):
            if self.fat_get(fat, n) == 0:
                chain.append(n)
                if len(chain) == nclusters:
                    break
        if len(chain) < nclusters:
            raise ValueError(f"out of FAT space: need {nclusters} clusters, found {len(chain)}")
        for a, b in zip(chain, chain[1:]):
            self.fat_set(fat, a, b)
        self.fat_set(fat, chain[-1], self.eoc())
        return chain

    def write_file(self, dirbuf, name83, payload):
        """Replace or create `name83` with `payload` (root dir only)."""
        fat = self.read_fat()
        idx, entry = self.find_entry(dirbuf, name83)

        # make room: free the old chain (existing file) first
        if entry is not None:
            (start,) = struct.unpack_from("<H", entry, 26)
            if start >= 2:
                self.free_chain(fat, start)

        needed = (len(payload) + self.cluster_bytes - 1) // self.cluster_bytes
        if self.count_free(fat) < needed:
            raise ValueError(
                f"not enough free clusters: need {needed}, have {self.count_free(fat)}")
        chain = self.allocate(fat, needed)
        for i, n in enumerate(chain):
            chunk = payload[i * self.cluster_bytes : (i + 1) * self.cluster_bytes]
            self._write(self.cluster_off(n), chunk.ljust(self.cluster_bytes, b"\x00"))

        if entry is None:
            idx = next(i for i in range(0, len(dirbuf), 32)
                       if dirbuf[i] in (0x00, 0xE5))
            entry = bytearray(32)
            base, ext = (name83.split(".") + [""])[:2]
            entry[0:8] = base.upper().ljust(8).encode("ascii")
            entry[8:11] = ext.upper().ljust(3).encode("ascii")
            dirbuf[idx : idx + 32] = entry
        struct.pack_into("<H", dirbuf, idx + 26, chain[0])
        struct.pack_into("<I", dirbuf, idx + 28, len(payload))
        dirbuf[idx + 11] = 0x20  # archive bit

        self.write_fats(fat)
        self.write_dir(dirbuf)

    def delete_file(self, dirbuf, name83):
        fat = self.read_fat()
        idx, entry = self.find_entry(dirbuf, name83)
        if entry is None:
            return False
        (start,) = struct.unpack_from("<H", entry, 26)
        if start >= 2:
            self.free_chain(fat, start)
        dirbuf[idx] = 0xE5
        self.write_fats(fat)
        self.write_dir(dirbuf)
        return True


# --------------------------------------------------------------------------
# GPT
# --------------------------------------------------------------------------

def parse_gpt(fileobj, size):
    fileobj.seek(512)
    hdr = fileobj.read(92)
    if hdr[:8] != b"EFI PART":
        raise ValueError("no GPT header")
    ent_lba, n_entries, ent_size = struct.unpack_from("<QII", hdr, 72)
    fileobj.seek(ent_lba * SECTOR)
    parts = []
    for i in range(n_entries):
        e = fileobj.read(ent_size)
        if e[:16] == b"\x00" * 16:
            continue
        first, last = struct.unpack_from("<QQ", e, 32)
        name = e[56:128].decode("utf-16-le").split("\x00")[0]
        parts.append({"index": len(parts) + 1, "label": name,
                      "first": first, "last": last,
                      "off": first * SECTOR, "bytes": (last - first + 1) * SECTOR})
    return parts


# --------------------------------------------------------------------------
# script.bin sanity (same format the firmware builder validates)
# --------------------------------------------------------------------------

def parse_script_bin_length(buf):
    (sections,) = struct.unpack_from("<I", buf, 0)
    if sections == 0 or sections > 0x100:
        raise ValueError("bad section count")
    return len(buf)


def main():
    ap = argparse.ArgumentParser(
        description="Install goodluckOS onto a GamiJa R36S stock card image "
                    "(file-swap install; see docs/r36s-stock-layout.md).")
    ap.add_argument("--target", required=True, help="stock card image file (or device)")
    ap.add_argument("--uimage", help="goodluckOS uImage (from kernel build) to install into p3")
    ap.add_argument("--rootfs-file", help="goodluckOS rootfs image to write into a partition")
    ap.add_argument("--rootfs-part", default="rootfs", choices=["rootfs", "emusystem"],
                    help="partition label to receive --rootfs-file (default: rootfs)")
    ap.add_argument("--root", default=DEFAULT_ROOT, help=f"root= kernel arg (default {DEFAULT_ROOT})")
    ap.add_argument("--keep-initrd", action="store_true", help="do not delete stock uInitrd")
    ap.add_argument("--backup-dir", default=None, help="where to store stock p3 files (default: alongside target)")
    ap.add_argument("--write", action="store_true", help="actually modify the target (default: plan only)")
    ap.add_argument("--skip-scriptbin-check", action="store_true",
                    help="DANGER: skip the script.bin identity check")
    ap.add_argument("--expect-scriptbin", default=SCRIPT_BIN_KNOWN_SHA256, metavar="SHA256",
                    help="expected script.bin sha256 (default: the pinned GamiJa stock hash; "
                         "override only for test fixtures or newly verified revisions)")
    args = ap.parse_args()

    target = args.target
    size = os.path.getsize(target)
    is_device = target.startswith("/dev/")
    mode = "r+b" if args.write else "rb"
    f = open(target, mode)

    plan = args.write is False
    log = lambda s: print(s)

    if is_device:
        log(f"WARNING: {target} is a block device.")
        if plan:
            log("         Running in plan mode; re-run with --write to modify.")
        else:
            log("         Make sure this is the STOCK card and you have a separate backup!")
        # refuse if mounted
        mounts = open("/proc/mounts").read()
        for line in mounts.splitlines():
            if line.split()[0] == target:
                raise SystemExit(f"REFUSING: {target} is mounted ({line.split()[1]}). Unmount first.")

    log(f"Target: {target} ({size} bytes, {size / 1048576:.0f} MiB) [{'WRITE' if args.write else 'PLAN'}]")
    log("")

    # ---- 1. partitions ---------------------------------------------------
    parts = parse_gpt(f, size)
    labels = {p["label"]: p for p in parts}
    log(f"GPT partitions: " + ", ".join(f"p{p['index']}:{p['label']}" for p in parts))
    for need in ("env", "boot"):
        if need not in labels:
            raise SystemExit(f"REFUSING: partition '{need}' not found (labels: {list(labels)})")

    # ---- 2. script.bin identity gate --------------------------------------
    f.seek(SCRIPT_BIN_OFFSET)
    sb = f.read(SCRIPT_BIN_MAX_LENGTH)
    try:
        parse_script_bin_length(sb)
        sb_hash = hashlib.sha256(sb[:42900]).hexdigest()
    except (ValueError, struct.error) as e:
        raise SystemExit(f"REFUSING: no valid script.bin at byte {SCRIPT_BIN_OFFSET} ({e})")
    if sb_hash != args.expect_scriptbin and not args.skip_scriptbin_check:
        raise SystemExit(
            "REFUSING: this card's script.bin does not match the verified GamiJa\n"
            "         stock hash. Either this is not a GamiJa R36S card or it ships\n"
            "         a different firmware revision. Refusing to touch it.\n"
            f"         measured: {sb_hash}\n"
            f"         expected: {args.expect_scriptbin}\n"
            "         (report it to https://github.com/CodeZombie/goodluckOS/issues/99)")
    log(f"script.bin @ byte {SCRIPT_BIN_OFFSET}: SHA-256 matches the verified GamiJa stock hash. OK")
    log("")

    # ---- 3. backup stock p3 ------------------------------------------------
    boot = labels["boot"]
    fat = FatVolume(f, boot["off"], (boot["last"] - boot["first"] + 1))
    dirbuf = bytearray(fat.read_dir())
    backup_dir = args.backup_dir or os.path.join(
        os.path.dirname(os.path.abspath(target)), "gaminja-stock-backup")
    for name83 in ("UIMAGE", "UINITRD"):
        idx, entry = fat.find_entry(dirbuf, name83)
        if entry is None:
            log(f"p3 has no {name83}")
            continue
        (start,) = struct.unpack_from("<H", entry, 26)
        (fsize,) = struct.unpack_from("<I", entry, 28)
        data = fat.read_chain(fat.read_fat(), start, fsize)
        digest = hashlib.sha256(data).hexdigest()
        os.makedirs(backup_dir, exist_ok=True)
        out_path = os.path.join(backup_dir, f"p3_{name83.lower()}.bin")
        with open(out_path, "wb") as o:
            o.write(data)
        log(f"p3/{name83}: {fsize} bytes, sha256 {digest[:16]}... -> {out_path}")
    log("")

    # ---- 4. plan the writes ------------------------------------------------
    if args.uimage:
        upayload = open(args.uimage, "rb").read()
        if len(upayload) < 64 or struct.unpack_from(">I", upayload, 0)[0] != 0x27051956:
            raise SystemExit(f"REFUSING: {args.uimage} is not a uImage (bad magic).")
        ih_type = upayload[30]
        (ih_load,) = struct.unpack_from(">I", upayload, 16)
        if ih_type != 2:
            raise SystemExit(f"REFUSING: {args.uimage} is not a kernel uImage (type={ih_type}).")
        if ih_load != UIMAGE_LOAD:
            raise SystemExit(
                f"REFUSING: uImage load address is 0x{ih_load:08x}, expected 0x{UIMAGE_LOAD:08x}.\n"
                f"         The stock env fatloads to 0x{FATLOAD_TARGET:08X} (header 0x40 below load).")
        log(f"New uImage: {args.uimage} ({len(upayload)} bytes, load 0x{ih_load:08x})")
        log("p3 actions: replace UIMAGE contents" + ("" if args.keep_initrd else ", delete UINITRD"))

    env_pairs = {
        "bootcmd": f"fatload sunxi_flash boot {FATLOAD_TARGET:08x} uImage; bootm {FATLOAD_TARGET:08x}",
        "bootargs": f"console=ttyS0,115200 root={args.root} rootfstype=ext4 rootwait rw panic=10",
        "bootdelay": "0",
        "console": "ttyS0,115200",
    }
    if args.rootfs_file:
        rp = labels.get(args.rootfs_part)
        if rp is None:
            raise SystemExit(f"REFUSING: partition '{args.rootfs_part}' not found")
        rf_size = os.path.getsize(args.rootfs_file)
        if rf_size > rp["bytes"]:
            raise SystemExit(
                f"REFUSING: rootfs image is {rf_size} bytes but partition "
                f"'{args.rootfs_part}' is only {rp['bytes']} bytes.")
        log(f"rootfs: {args.rootfs_file} ({rf_size} bytes) -> partition "
            f"'{args.rootfs_part}' (p{rp['index']}, {rp['bytes']} bytes)")
    log("")
    log(f"New env partition contents:")
    for line in build_env_text(env_pairs).decode("ascii").split("\0"):
        if line:
            log(f"    {line}")
    log("")

    if plan:
        log("PLAN ONLY - nothing was modified. Re-run with --write to apply.")
        return 0

    # ---- 5. apply ----------------------------------------------------------
    if args.uimage:
        if not args.keep_initrd:
            fat.delete_file(dirbuf, "UINITRD")
            log("p3: deleted UINITRD")
        fat.write_file(dirbuf, "UIMAGE", upayload)
        log(f"p3: wrote new UIMAGE ({len(upayload)} bytes)")

        # verify by reading back through the FAT
        fat2 = FatVolume(f, boot["off"], (boot["last"] - boot["first"] + 1))
        dir2 = fat2.read_dir()
        idx, entry = fat2.find_entry(dir2, "UIMAGE")
        (start,) = struct.unpack_from("<H", entry, 26)
        (fsize,) = struct.unpack_from("<I", entry, 28)
        back = fat2.read_chain(fat2.read_fat(), start, fsize)
        back_hash = hashlib.sha256(back).hexdigest()
        want_hash = hashlib.sha256(upayload).hexdigest()
        ok = back_hash == want_hash
        log(f"verify: read-back sha256 {'MATCHES' if ok else 'MISMATCH'} ({back_hash[:16]}...)")
        if not ok:
            raise SystemExit("ERROR: uImage read-back does not match; the FAT write failed.")

    env_block = build_env_block(env_pairs, labels["env"]["bytes"])
    f.seek(labels["env"]["off"])
    f.write(env_block)
    f.flush()
    f.seek(labels["env"]["off"])
    check = f.read(labels["env"]["bytes"])
    log(f"env: rewritten ({len(check)} bytes), CRC {'OK' if verify_env_block(check) else 'BAD'}")
    if not verify_env_block(check):
        raise SystemExit("ERROR: env rewrite failed CRC verification.")

    if args.rootfs_file:
        rp = labels[args.rootfs_part]
        rf_size = os.path.getsize(args.rootfs_file)
        done = 0
        with open(args.rootfs_file, "rb") as src:
            while True:
                chunk = src.read(4 * 1024 * 1024)
                if not chunk:
                    break
                f.seek(rp["off"] + done)
                f.write(chunk)
                done += len(chunk)
                print(f"\rrootfs: {done / 1048576:.0f}/{rf_size / 1048576:.0f} MiB", end="", flush=True)
        print()
        log("rootfs: written")

    f.close()
    log("")
    log("Install complete. Next steps on hardware:")
    log("  - serial console: ttyS0 @ 115200 (USB TTY port)")
    log("  - if the screen stays black: retry with the panel2 uImage")
    return 0


if __name__ == "__main__":
    sys.exit(main())
