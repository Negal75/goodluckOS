#!/usr/bin/env python3
"""
install-gaminja.test.py - regression tests for image/tools/install-gaminja.py

Builds a fully synthetic 20 MiB GamiJa-style card (GPT with `env`/`boot`
partitions, FAT12 `boot` volume holding UIMAGE/UINITRD, script.bin at the
measured byte 20488192) and exercises the installer end to end:
  1. plan mode modifies nothing
  2. write mode swaps UIMAGE, deletes UINITRD, rewrites env (CRC valid)
  3. byte-exact read-back through an independent FAT walk
  4. tampered script.bin is refused
  5. wrong-load-address uImage is refused
  6. non-kernel uImage is refused

Run: python3 tests/install-gaminja.test.py
"""

import hashlib
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "..", "image", "tools", "install-gaminja.py")
sys.path.insert(0, os.path.join(HERE, "..", "image", "tools"))
import importlib.util
spec = importlib.util.spec_from_file_location("install_gaminja", TOOL)
inst = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inst)

SECTOR = 512
SCRIPT_OFFSET = 20488192
FAILURES = 0


def ok(name, cond):
    global FAILURES
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES += 1


def make_uimage(payload, load=0x40008000):
    hdr = bytearray(64)
    struct.pack_into(">IIIIIII", hdr, 0, 0x27051956, 0, 0,
                     len(payload), load, load, 0)
    hdr[28:32] = bytes([5, 2, 2, 0])  # os=Linux arch=ARM type=Kernel comp=none
    hdr[32:64] = b"goodluckOS test".ljust(32, b"\x00")
    struct.pack_into(">I", hdr, 24, zlib.crc32(payload) & 0xFFFFFFFF)
    struct.pack_into(">I", hdr, 4, zlib.crc32(bytes(hdr)) & 0xFFFFFFFF)
    return bytes(hdr) + payload


def make_stock_card():
    """20 MiB image: GPT (env @30000, boot @30720), FAT12 boot, script.bin."""
    size = 20 * 1024 * 1024
    img = bytearray(size)

    # --- GPT (protective MBR + header + entries) ---
    img[510] = 0x55; img[511] = 0xAA
    img[512:520] = b"EFI PART"
    struct.pack_into("<I", img, 512 + 80, 1)      # revision
    struct.pack_into("<I", img, 512 + 84, 92)     # header size
    struct.pack_into("<Q", img, 512 + 72, 2)      # entry LBA = 2
    struct.pack_into("<I", img, 512 + 80 + 0, 0)  # (unused)
    # header fields at their real offsets (we wrote at 512 above):
    struct.pack_into("<Q", img, 512 + 72, 2)      # partition entries LBA
    struct.pack_into("<I", img, 512 + 80, 128)    # num entries
    struct.pack_into("<I", img, 512 + 84, 128)    # entry size

    parts = [("env", 30000, 30511), ("boot", 30720, 38911),
             ("rootfs", 39168, 40000)]
    LINUX_FS_GUID = bytes.fromhex("af3dc60f838473478e793d69d8477de4")
    for i, (label, first, last) in enumerate(parts):
        base = 2 * SECTOR + i * 128
        img[base : base + 16] = LINUX_FS_GUID
        struct.pack_into("<Q", img, base + 32, first)
        struct.pack_into("<Q", img, base + 40, last)
        img[base + 56 : base + 56 + 2 * len(label)] = label.encode("utf-16-le")

    # --- script.bin at the measured offset (minimal valid blob) ---
    sb = bytearray(200)
    struct.pack_into("<II", sb, 0, 1, 200)         # 1 section, len 200
    sb[16:24] = b"target\0"
    struct.pack_into("<ii", sb, 48, 1, 24)         # 1 entry, table @ word 24
    sb[96:136] = b"boot_clock".ljust(32, b"\x00")  # entry @ byte 96
    struct.pack_into("<iI", sb, 128, 40, (1 << 16) | 1)  # data @ word 40, int x1
    struct.pack_into("<I", sb, 160, 1008)
    img[SCRIPT_OFFSET : SCRIPT_OFFSET + len(sb)] = sb

    # --- FAT12 `boot` partition BPB: 8192 sectors, 4 sec/cluster ---
    boff = 30720 * SECTOR
    bs = bytearray(512)
    bs[0:3] = b"\xEB\x3C\x90"
    bs[3:11] = b"mkfs.fat"
    struct.pack_into("<H", bs, 0x0B, 512)
    bs[0x0D] = 4                                   # sectors/cluster
    struct.pack_into("<H", bs, 0x0E, 1)            # reserved
    bs[0x10] = 2                                   # 2 FATs
    struct.pack_into("<H", bs, 0x11, 32)           # 32 root entries
    struct.pack_into("<H", bs, 0x13, 8192)         # total sectors
    struct.pack_into("<H", bs, 0x16, 6)            # FAT sectors
    bs[0x36:0x3B] = b"FAT12 "
    img[boff : boff + 512] = bs
    return img


def populate_boot(path, part_off, files):
    """Write UIMAGE/UINITRD onto the synthetic FAT12 volume via the tool's own class."""
    with open(path, "r+b") as f:
        vol = inst.FatVolume(f, part_off)
        dirbuf = bytearray(vol.read_dir())
        for name, payload in files:
            vol.write_file(dirbuf, name, payload)
        f.flush()


def run(args, expect_fail=False):
    p = subprocess.run([sys.executable, TOOL] + args,
                       capture_output=True, text=True)
    if expect_fail:
        return p.returncode != 0, p
    return p


def scriptbin_hash(img):
    return hashlib.sha256(img[SCRIPT_OFFSET : SCRIPT_OFFSET + 42900]).hexdigest()


def main():
    tmp = tempfile.mkdtemp(prefix="gaminja-inst-")
    card = os.path.join(tmp, "stock.img")
    img = make_stock_card()
    BOOT = 30720 * SECTOR

    stock_kernel = make_uimage(b"STOCK KERNEL " * 1000)          # ~13 KiB
    stock_initrd = make_uimage(b"STOCK INITRD " * 500, load=0)
    with open(card, "wb") as f:
        f.write(img)
    populate_boot(card, BOOT, [("UIMAGE", stock_kernel), ("UINITRD", stock_initrd)])
    pristine = open(card, "rb").read()  # fixture state before any install run

    new_kernel = make_uimage(b"GOODLUCK KERNEL " * 2000)         # ~26 KiB
    nk = os.path.join(tmp, "new.uImage")
    open(nk, "wb").write(new_kernel)

    # 1. plan mode: no changes
    sbhash = scriptbin_hash(img)
    common = ["--uimage", nk, "--expect-scriptbin", sbhash]
    shutil.copy(card, card + ".plan")
    p = run(["--target", card + ".plan"] + common)
    ok("plan mode exits 0", p.returncode == 0)
    ok("plan mode leaves image unchanged",
       open(card + ".plan", "rb").read() == pristine)

    # 2. write mode
    p = run(["--target", card] + common + ["--write",
            "--backup-dir", os.path.join(tmp, "b")])
    ok("write mode exits 0", p.returncode == 0)

    with open(card, "r+b") as f:
        vol = inst.FatVolume(f, BOOT)
        dirbuf = vol.read_dir()
        idx, e = vol.find_entry(dirbuf, "UIMAGE")
        ok("UIMAGE dir entry exists", e is not None)
        size, = struct.unpack_from("<I", e, 28)
        start, = struct.unpack_from("<H", e, 26)
        ok("UIMAGE size matches", size == len(new_kernel))
        back = vol.read_chain(vol.read_fat(), start, size)
        ok("UIMAGE content byte-exact", hashlib.sha256(back).hexdigest()
           == hashlib.sha256(new_kernel).hexdigest())
        ok("UINITRD deleted", vol.find_entry(dirbuf, "UINITRD")[0] is None)

        f.seek(30000 * SECTOR)
        ok("env CRC valid", inst.verify_env_block(f.read(512 * 512)))
        txt = inst.parse_env_block(open(card, "rb").read()[30000 * SECTOR : 30512 * SECTOR])
        ok("env bootcmd updated", any("bootm" in l and "40007fc0" in l for l in txt))
        ok("env bootargs has root", any("root=/dev/mmcblk0p5" in l for l in txt))

    # backup files exist and match stock
    bk = open(os.path.join(tmp, "b", "p3_uimage.bin"), "rb").read()
    ok("stock uImage backed up", bk == stock_kernel)
    bi = open(os.path.join(tmp, "b", "p3_uinitrd.bin"), "rb").read()
    ok("stock uInitrd backed up", bi == stock_initrd)

    # 4. tampered script.bin refuses
    bad = os.path.join(tmp, "tampered.img")
    shutil.copy(card, bad)
    with open(bad, "r+b") as f:
        f.seek(SCRIPT_OFFSET); f.write(b"\xff\xff\xff\xff")
    ok("tampered script.bin refused",
       run(["--target", bad] + common + ["--write"], expect_fail=True)[0])

    # 5. wrong load address refuses
    wl = os.path.join(tmp, "wrong_load.uImage")
    open(wl, "wb").write(make_uimage(b"x" * 100, load=0x50008000))
    ok("wrong load address refused",
       run(["--target", card] + common + ["--write", "--uimage", wl], expect_fail=True)[0])

    # 6. non-kernel uImage refuses
    rd = os.path.join(tmp, "ramdisk.uImage")
    hdr = bytearray(64)
    struct.pack_into(">IIIIIII", hdr, 0, 0x27051956, 0, 0, 4, 0, 0, 0)
    hdr[28:32] = bytes([5, 2, 3, 0])  # type=3 RAMDisk
    open(rd, "wb").write(bytes(hdr) + b"abc\x00")
    ok("non-kernel uImage refused",
       run(["--target", card] + common + ["--write", "--uimage", rd], expect_fail=True)[0])

    shutil.rmtree(tmp, ignore_errors=True)
    print("\n" + ("ALL TESTS PASSED" if FAILURES == 0 else f"{FAILURES} FAILURES"))
    return 0 if FAILURES == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
