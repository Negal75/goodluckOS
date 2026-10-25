#!/usr/bin/env python3
"""
analyze-gaminja-dump.py - GamiJa R36S (Batocera clone) stock SD card analyzer

GOODLUCKOS PORT TOOLING -- see docs/gaminja-r36s.md and issue #99.

The GamiJa R36S clones run a Batocera-like firmware with a bootloader layout
that differs from the GA36-MB stock cards. Notably (from issue #99):

    GA36-MB:    script.bin at byte offset 20340736
    GamiJa:     script.bin at byte offset 20488192

and the kernel (or boot image) is expected to be elsewhere too. Before
goodluckOS can build/flash images for this device we need a full map of the
stock layout. This tool produces that map from the dump you already have.

What it looks for:
  - MBR partition table / GPT signature
  - sunxi boot images: boot0 ("eGON.BT0"), boot1/u-boot ("eGON")
  - android-style boot images ("ANDROID!")
  - script.bin blobs (parsed and section-listed; convertible via sunxi-fexc)
  - anything else that looks like an embedded boot component

Usage:
    ./analyze-gaminja-dump.py <stock_sdcard.img> [--extract <outdir>] [--full]

By default only the first --max-megabytes (default 512) are scanned, which is
far beyond anything a bootloader layout needs. Pass --full for a complete
sweep of larger dumps.

Output: a text report on stdout. With --extract, copies script.bin / boot0
payload slices into <outdir> for upload to issue #99.
"""

import argparse
import os
import re
import struct
import sys
import hashlib

SCRIPT_BIN_HEADER = 16
SCRIPT_BIN_SECTION_STRUCT = 40
SCRIPT_BIN_ENTRY_STRUCT = 40
SCRIPT_BIN_SECTION_LIMIT = 0x100
SCRIPT_BIN_MAX_LENGTH = 131072

SECTOR = 512

NAME_RE = re.compile(rb"^[\x20-\x7e]{3,}\x00", re.DOTALL)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_script_bin(buf: bytes, offset: int, size: int) -> int:
    """Same structure parser as the firmware builder (docs/download.html).
    Returns content length or raises ValueError."""
    start = offset
    avail = size - start
    if avail < SCRIPT_BIN_HEADER:
        raise ValueError("too short")
    (sections,) = struct.unpack_from("<I", buf, start)
    if sections == 0 or sections > SCRIPT_BIN_SECTION_LIMIT:
        raise ValueError(f"unreasonable section count ({sections})")
    max_end = SCRIPT_BIN_HEADER + sections * SCRIPT_BIN_SECTION_STRUCT
    if max_end > avail:
        raise ValueError("section table runs past region end")
    for i in range(sections):
        s_off = start + SCRIPT_BIN_HEADER + i * SCRIPT_BIN_SECTION_STRUCT
        entry_count, table_off_words = struct.unpack_from("<ii", buf, s_off + 32)
        if entry_count < 0 or table_off_words < 0:
            raise ValueError(f"negative section {i} fields")
        if not NAME_RE.match(buf[s_off : s_off + 32]):
            raise ValueError(f"garbage section {i} name")
        table_off = table_off_words * 4
        table_end = table_off + entry_count * SCRIPT_BIN_ENTRY_STRUCT
        if table_end > avail:
            raise ValueError(f"section {i} entry table out of bounds")
        max_end = max(max_end, table_end)
        for j in range(entry_count):
            e_off = start + table_off + j * SCRIPT_BIN_ENTRY_STRUCT
            data_off_words, words = struct.unpack_from("<iI", buf, e_off + 32)
            if data_off_words < 0:
                raise ValueError(f"negative entry {i}.{j} offset")
            if not NAME_RE.match(buf[e_off : e_off + 32]):
                raise ValueError(f"garbage entry {i}.{j} name")
            data_end = data_off_words * 4 + (words & 0xFFFF) * 4
            if data_end > avail:
                raise ValueError(f"entry {i}.{j} data out of bounds")
            max_end = max(max_end, data_end)
    return max_end


def describe_partition_table(f) -> list:
    f.seek(0)
    mbr = f.read(1024)
    lines = []
    if len(mbr) < 512 or mbr[510:512] != b"\x55\xaa":
        lines.append("MBR: no 0x55AA signature at byte 510 (unusual!)")
    else:
        lines.append("MBR: 0x55AA signature at byte 510")
        for p in range(4):
            e = 446 + p * 16
            ptype = mbr[e + 4]
            if ptype == 0:
                continue
            start, count = struct.unpack_from("<II", mbr, e + 8)
            lines.append(
                f"MBR: partition {p+1}: type=0x{ptype:02x} start={start} sectors "
                f"({start * SECTOR / 1048576:.1f} MiB) count={count} sectors "
                f"({count * SECTOR / 1048576:.1f} MiB)"
            )
    if len(mbr) >= 520 and mbr[512:520] == b"EFI PART":
        lines.append('GPT: "EFI PART" header found at LBA 1')
    return lines


def find_markers(buf: bytes, markers: dict) -> dict:
    """markers: sig bytes -> list of names. Returns name -> [sector-aligned offsets]."""
    hits = {n: [] for names in markers.values() for n in names}
    for sig, names in markers.items():
        start = 0
        while True:
            i = buf.find(sig, start)
            if i < 0:
                break
            if i % SECTOR == 0:
                for n in names:
                    if i not in hits[n]:
                        hits[n].append(i)
            start = i + 1
    return hits


def find_script_bin_candidates(buf: bytes) -> list:
    candidates = []
    for off in range(0, len(buf) - SCRIPT_BIN_HEADER, 4096):
        try:
            length = parse_script_bin(buf, off, len(buf))
        except ValueError:
            continue
        if length <= SCRIPT_BIN_MAX_LENGTH:
            candidates.append((off, length))
    return candidates


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n\n")[0])
    ap.add_argument("image", help="path to the raw stock microSD dump")
    ap.add_argument("--extract", metavar="DIR", help="extract script.bin / boot payloads here")
    ap.add_argument("--full", action="store_true", help="scan the entire dump (slow)")
    ap.add_argument("--max-megabytes", type=int, default=512, help="bytes to scan without --full (default 512)")
    args = ap.parse_args()

    size = os.path.getsize(args.image)
    limit = size if args.full else min(size, args.max_megabytes * 1024 * 1024)
    limit -= limit % SECTOR

    lines = []
    lines.append("goodluckOS GamiJa stock-dump analysis")
    lines.append(f"Image: {args.image} ({size} bytes, {size / 1048576:.1f} MiB)")
    lines.append(f"Scanned: first {limit} bytes ({limit / 1048576:.1f} MiB)" + (" [FULL]" if args.full else ""))
    lines.append("")

    with open(args.image, "rb", buffering=0) as f:
        lines.append("-- Partition table --")
        lines.extend(describe_partition_table(f))
        lines.append("")

        f.seek(0)
        buf = f.read(limit)

        lines.append("-- Bootloader/kernel markers (sector-aligned) --")
        marker_map = {
            b"eGON.BT0": ["boot0"],
            b"eGON": ["boot1/u-boot", "boot0"],
            b"ANDROID!": ["android boot image (ANDROID!)"],
            b"\x27\x05\x19\x56": ["legacy uImage (u-boot bootm)"],
        }
        hits = find_markers(buf, marker_map)
        for name in ["boot0", "boot1/u-boot", "android boot image (ANDROID!)", "legacy uImage (u-boot bootm)"]:
            offs = hits.get(name, [])
            if offs:
                shown = [str(o) for o in offs[:16]]
                lines.append(f"{name}: {len(offs)} hit(s) at bytes [{', '.join(shown)}{'...' if len(offs) > 16 else ''}]")
                lines.append(f"              = sectors [{', '.join(str(o // SECTOR) for o in offs[:16])}{'...' if len(offs) > 16 else ''}]")
                lines.append(f"              = MiB [{', '.join(f'{o / 1048576:.2f}' for o in offs[:16])}{'...' if len(offs) > 16 else ''}]")
        if not any(hits.values()):
            lines.append("No boot markers found in scanned region.")
        lines.append("")

        lines.append("-- script.bin candidates (4 KiB-aligned scan) --")
        cands = find_script_bin_candidates(buf)
        if not cands:
            lines.append("None found.")
        for off, length in cands[:8]:
            payload = buf[off : off + length]
            lines.append(f"script.bin at byte {off} (sector {off // SECTOR}, {off / 1048576:.3f} MiB), "
                         f"length {length}, sha256 {sha256(payload)}")
            # Section name dump (first 12) to help identify the device/fex.
            try:
                (sections,) = struct.unpack_from("<I", payload, 0)
                names = []
                for i in range(min(sections, 12)):
                    s_off = SCRIPT_BIN_HEADER + i * SCRIPT_BIN_SECTION_STRUCT
                    name_bytes = payload[s_off : s_off + 32].split(b"\x00", 1)[0]
                    try:
                        names.append(name_bytes.decode("ascii"))
                    except UnicodeDecodeError:
                        continue
                lines.append(f"  sections ({sections}): {', '.join(names)}")
            except Exception:
                pass
        lines.append("")
        lines.append("script.bin converts to .fex for inspection with: sunxi-fexc -u script.bin out.fex")
        lines.append("Please attach this report (and the extracted script.bin, if --extract) to:")
        lines.append("  https://github.com/CodeZombie/goodluckOS/issues/99")

    report = "\n".join(lines) + "\n"
    print(report)

    if args.extract:
        outdir = args.extract
        os.makedirs(outdir, exist_ok=True)
        written = []
        for off, length in cands[:4]:
            name = f"script_{off}.bin"
            with open(os.path.join(outdir, name), "wb") as o:
                o.write(buf[off : off + length])
            written.append(name)
        # boot0 is a small bootrom-loaded stub; keep an 8-sector slice for reference.
        for off in hits.get("boot0", [])[:2]:
            out = os.path.join(outdir, f"boot0_{off}.bin")
            with open(out, "wb") as o:
                o.write(buf[off : off + SECTOR * 8])
            written.append(os.path.basename(out))
        with open(os.path.join(outdir, "layout_report.txt"), "w") as o:
            o.write(report)
        print(f"Extracted: {', '.join(written)} -> {outdir}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
