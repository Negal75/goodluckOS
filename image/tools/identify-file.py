#!/usr/bin/env python3
"""
identify-file.py - universal firmware-blob identifier (goodluckOS port tooling)

Some stock cards (e.g. GamiJa R36S Batocera clones, issue #99) mount on a PC
and expose individual files - magic.bin, boot.scr, extlinux.conf, uImage,
zImage, ... - instead of (or in addition to) a raw-bootloader layout. Point
this tool at ANY of those files and it will identify what it is, decode as
much as possible, and print what to do next.

Usage:
    ./identify-file.py <file> [--extract <dir>]

Identifies and decodes:
  - sunxi script.bin  (same parser as the firmware builder; suggests sunxi-fexc)
  - sunxi .fex text   (a fex lists the SoC clock, LCD and button wiring
                       directly - gold for building the device tree)
  - android boot image ("ANDROID!" header -> kernel size/load address)
  - legacy u-boot uImage (auto-text-dumps Script payloads such as
                       boot.scr, which usually reveal exactly which file
                       the bootloader loads as the kernel)
  - FIT / device tree (0xd00dfeed -> "run dtc -I dtb -O dts")
  - squashfs / ext filesystem / FAT boot sectors
  - boot0 / boot1 (eGON.BT0 / eGON)
  - anything unrecognized: entropy, hexdump, printable strings for the
    issue report
"""

import argparse
import math
import os
import re
import struct
import sys
import hashlib

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counts = {}
    sample = data[: 1 << 20]
    for b in sample:
        counts[b] = counts.get(b, 0) + 1
    total = len(sample)
    ent = 0.0
    for c in counts.values():
        p = c / total
        ent -= p * math.log2(p)
    return ent


def hexdump(data: bytes, start: int = 0, length: int = 160) -> list:
    lines = []
    for i in range(0, min(length, len(data)), 16):
        chunk = data[i : i + 16]
        hexs = " ".join(f"{b:02x}" for b in chunk)
        text = "".join(chr(b) if 0x20 <= b < 0x7F else "." for b in chunk)
        lines.append(f"  {start + i:08x}  {hexs:<47}  |{text}|")
    return lines


def ascii_strings(data: bytes, min_len: int = 8, limit: int = 40) -> list:
    out = []
    for m in re.finditer(rb"[\x20-\x7e]{%d,}" % min_len, data):
        out.append(m.group().decode("ascii"))
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------- script.bin
SCRIPT_BIN_HEADER = 16
SCRIPT_BIN_SECTION_STRUCT = 40
SCRIPT_BIN_ENTRY_STRUCT = 40
SCRIPT_BIN_SECTION_LIMIT = 0x100
SCRIPT_BIN_MAX_LENGTH = 131072
NAME_RE = re.compile(rb"^[\x20-\x7e]{3,}\x00", re.DOTALL)


def parse_script_bin(buf: bytes) -> int:
    if len(buf) < SCRIPT_BIN_HEADER:
        raise ValueError("too short")
    (sections,) = struct.unpack_from("<I", buf, 0)
    if sections == 0 or sections > SCRIPT_BIN_SECTION_LIMIT:
        raise ValueError(f"unreasonable section count ({sections})")
    max_end = SCRIPT_BIN_HEADER + sections * SCRIPT_BIN_SECTION_STRUCT
    if max_end > len(buf):
        raise ValueError("section table runs past end")
    for i in range(sections):
        s_off = SCRIPT_BIN_HEADER + i * SCRIPT_BIN_SECTION_STRUCT
        entry_count, table_off_words = struct.unpack_from("<ii", buf, s_off + 32)
        if entry_count < 0 or table_off_words < 0:
            raise ValueError(f"negative section {i} fields")
        if not NAME_RE.match(buf[s_off : s_off + 32]):
            raise ValueError(f"garbage section {i} name")
        table_end = table_off_words * 4 + entry_count * SCRIPT_BIN_ENTRY_STRUCT
        if table_end > len(buf):
            raise ValueError(f"section {i} entry table out of bounds")
        max_end = max(max_end, table_end)
        for j in range(entry_count):
            e_off = table_off_words * 4 + j * SCRIPT_BIN_ENTRY_STRUCT
            data_off_words, words = struct.unpack_from("<iI", buf, e_off + 32)
            if data_off_words < 0:
                raise ValueError(f"negative entry {i}.{j}")
            if not NAME_RE.match(buf[e_off : e_off + 32]):
                raise ValueError(f"garbage entry {i}.{j} name")
            data_end = data_off_words * 4 + (words & 0xFFFF) * 4
            if data_end > len(buf):
                raise ValueError(f"entry {i}.{j} data out of bounds")
            max_end = max(max_end, data_end)
    return max_end


def script_bin_sections(buf: bytes) -> list:
    (sections,) = struct.unpack_from("<I", buf, 0)
    names = []
    for i in range(sections):
        s_off = SCRIPT_BIN_HEADER + i * SCRIPT_BIN_SECTION_STRUCT
        name = buf[s_off : s_off + 32].split(b"\x00", 1)[0].decode("ascii", "replace")
        entry_count, _ = struct.unpack_from("<ii", buf, s_off + 32)
        names.append(f"{name}({entry_count})")
    return names


# ------------------------------------------------------------------- uImage
UIMG_TYPES = {1: "Standalone", 2: "Kernel", 5: "RAMDisk", 6: "Multi-File",
              7: "Firmware", 8: "Script", 9: "Filesystem"}
UIMG_OS = {0: "Invalid", 5: "Linux", 17: "OpenRTOS"}
UIMG_COMP = {0: "none", 1: "gzip", 2: "bzip2", 3: "lzma", 4: "lzo", 5: "lz4"}


def parse_uimage(buf: bytes) -> dict:
    if len(buf) < 64 or struct.unpack_from(">I", buf, 0)[0] != 0x27051956:
        raise ValueError("not a uImage")
    ih_size, ih_load, ih_ep = struct.unpack_from(">III", buf, 12)
    ih_os, ih_arch, ih_type, ih_comp = buf[28], buf[29], buf[30], buf[31]
    name = struct.unpack_from("<32s", buf, 32)[0].split(b"\x00", 1)[0].decode("ascii", "replace")
    return {
        "name": name,
        "size": ih_size,
        "load": ih_load,
        "entry": ih_ep,
        "os": UIMG_OS.get(ih_os, f"?(os={ih_os})"),
        "arch": "ARM" if ih_arch == 2 else f"?(arch={ih_arch})",
        "type": UIMG_TYPES.get(ih_type, f"?(type={ih_type})"),
        "comp": UIMG_COMP.get(ih_comp, f"?(comp={ih_comp})"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--extract", metavar="DIR", help="write decoded payloads here")
    args = ap.parse_args()

    size = os.path.getsize(args.file)
    cap = min(size, 64 * 1024 * 1024)
    with open(args.file, "rb") as f:
        buf = f.read(cap)

    lines = [f"goodluckOS firmware-blob identification",
             f"File: {args.file} ({size} bytes, {size / 1024:.1f} KiB)",
             f"SHA-256 (of scanned prefix): {sha256(buf)}"]
    if cap < size:
        lines.append(f"(scanned the first {cap} bytes of a much larger file)")
    lines.append(f"Entropy (first MiB): {entropy(buf):.3f} bits/byte (~8.0 = compressed/random)")
    lines.append("")

    ident = None
    extract = None

    # 1) .fex plain text (prints its own content; most valuable first look)
    if buf[:1] == b"[":
        try:
            head = buf[:4096].decode("utf-8", "replace")
            first = [l.strip() for l in head.splitlines() if l.strip()][:4]
            lines.append(f"IDENTIFIED: plain-text config; begins: {'  |  '.join(first)}")
            lines.append("  If this is a .fex it lists the SoC clock, LCD config and button")
            lines.append("  wiring directly - attach the file itself to the issue!")
            print("\n".join(lines))
            print()
            print("---- first 8 KiB of text ----")
            print(buf[:8192].decode("utf-8", "replace"))
            return 0
        except UnicodeDecodeError:
            pass
        ident = "[text-like binary, not plain text]"

    # 2) sunxi script.bin
    if ident is None:
        try:
            length = parse_script_bin(buf)
            if length <= SCRIPT_BIN_MAX_LENGTH:
                ident = f"sunxi script.bin ({length} bytes of content)"
                lines.append(f"IDENTIFIED: {ident}")
                lines.append(f"  sections: {', '.join(script_bin_sections(buf))}")
                lines.append("  Convert for inspection with: sunxi-fexc -u <file> out.fex")
                extract = ("script_payload.bin", buf[:length])
        except ValueError:
            pass

    # 3) eGON stages
    if ident is None and buf[:8] == b"eGON.BT0":
        ident = "sunxi boot0 (eGON.BT0) - bootrom-loaded stage"
    elif ident is None and buf[:4] == b"eGON":
        ident = "sunxi boot1/u-boot stage (eGON-prefixed)"

    # 4) android boot image
    if ident is None and buf[:8] == b"ANDROID!":
        ksize, kaddr, ssize = struct.unpack_from("<III", buf, 8)
        ident = "android boot image"
        lines.append(f"IDENTIFIED: android boot image: kernel_size={ksize} kernel_addr=0x{kaddr:08x} second_size={ssize}")
        lines.append(f"  (dd flash offset is measured when analyzing the whole card; this file")
        lines.append(f"   identified by its header - kernel payload begins at byte 40)")

    # 5) legacy uImage (incl. boot.scr scripts)
    if ident is None:
        try:
            u = parse_uimage(buf)
            ident = "legacy u-boot uImage"
            payload = buf[64 : 64 + u["size"]]
            lines.append(f"IDENTIFIED: uImage name='{u['name']}' type={u['type']} os={u['os']} arch={u['arch']}")
            lines.append(f"  size={u['size']} load=0x{u['load']:08x} entry=0x{u['entry']:08x} comp={u['comp']}")
            if u["type"] == "Script":
                lines.append("  >>> A boot.scr-style U-Boot script! Its command text usually shows")
                lines.append("  >>> exactly which file/partition the kernel is loaded from.")
                lines.append("  ---- script body (first 4 KiB) ----")
                body = payload[:4096].decode("utf-8", "replace").replace("\x00", "")
                if body.strip():
                    lines.extend(body.splitlines())
                else:
                    lines.extend(hexdump(payload, 0, 160))
                extract = ("uboot-script.txt", payload)
            elif u["type"] == "Kernel":
                lines.append("  (this is the kernel image payload itself)")
                extract = ("kernel_payload.img", payload)
        except ValueError:
            pass

    # 6) DTB / FIT
    if ident is None and buf[:4] == b"\xd0\x0d\xfe\xed":
        ident = "FIT / flattened device tree (0xd00dfeed)"
        lines.append("IDENTIFIED: device tree blob")
        lines.append("  Decompile with: dtc -I dtb -O dts -o out.dts <file>")

    # 7) filesystem images
    if ident is None:
        if buf[:4] == b"hsqs":
            ident = "squashfs filesystem image"
        elif buf[:4] == b"qshs":
            ident = "squashfs filesystem image (big-endian)"
        elif len(buf) > 1084 and struct.unpack_from("<H", buf, 1024 + 56)[0] == 0xEF53:
            ident = "ext filesystem (ext2/3/4) raw section"

    if ident:
        if not any(l.startswith("IDENTIFIED") for l in lines):
            lines.append(f"IDENTIFIED: {ident}")
    else:
        lines.append("IDENTIFIED: unknown blob")
        lines.append("")
        lines.append("First 160 bytes:")
        lines.extend(hexdump(buf))
        lines.append("")
        lines.append("Printable strings:")
        for s in ascii_strings(buf):
            lines.append(f"  {s!r}")
        lines.append("")
        lines.append("If none of this means anything to you, attach the file and this")
        lines.append("output to https://github.com/CodeZombie/goodluckOS/issues/99")

    print("\n".join(lines) + "\n")

    if args.extract and extract:
        os.makedirs(args.extract, exist_ok=True)
        name, data = extract
        out = os.path.join(args.extract, name)
        with open(out, "wb") as o:
            o.write(data)
        print(f"Extracted: {out}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
