#!/usr/bin/env python3
"""
scriptbin2fex.py - convert a sunxi script.bin blob to .fex-style text
(offline stand-in for `sunxi-fexc -u`).

Layout (reverse-engineered from real files, cross-checked against
sunxi-tools' script.bin parser):

  header (16 B): u32 section_count, u32 total_len, ...
  section (40 B): name[32], entry_count s32, entry_table_off s32 (words)
  entry   (40 B): name[32], value_off s32 (words), packed u32 = (count<<16)|type

  type 1 = int list (count words), 2 = chars (count*4 B), 4 = GPIO
           (6 B: port, num, mul_sel, pull, drv, data), 5 = chars.
"""
import struct
import sys

HEADER = 16
STRUCT = 40
PORTS = "ABCDEFGH"


def fex(buf):
    out = []
    sections, = struct.unpack_from("<I", buf, 0)
    for i in range(sections):
        s = HEADER + i * STRUCT
        name = buf[s : s + 32].split(b"\x00", 1)[0].decode("ascii", "replace")
        count, off_words = struct.unpack_from("<ii", buf, s + 32)
        if count <= 0 or off_words <= 0:
            continue
        out.append(f"[{name}]\n")
        for j in range(count):
            e = off_words * 4 + j * STRUCT
            if e + STRUCT > len(buf):
                break
            ename = buf[e : e + 32].split(b"\x00", 1)[0].decode("ascii", "replace")
            data_off, packed = struct.unpack_from("<iI", buf, e + 32)
            if data_off <= 0:
                continue
            vtype, n = packed >> 16, packed & 0xFFFF
            d = data_off * 4
            if vtype == 1:  # int list
                vals = struct.unpack_from("<%dI" % min(n, (len(buf) - d) // 4), buf, d)
                text = " ".join(str(v) for v in vals)
            elif vtype in (2, 5):  # chars
                text = buf[d : d + n * 4].split(b"\x00", 1)[0].decode("ascii", "replace")
            elif vtype == 4:  # GPIO: port, num, mul_sel, pull, drv, data
                b = buf[d : d + 6]
                if len(b) >= 6 and 1 <= b[0] <= len(PORTS):
                    p = f"P{PORTS[b[0] - 1]}{b[1]:02d}"
                    text = f"port:{p}<{b[2]}><{b[3]}><default><{b[5]}>"
                else:
                    text = "gpio? " + b.hex(" ")
            else:
                text = "raw " + " ".join(f"{w:#x}" for w in struct.unpack_from("<%dI" % min(n or 1, 6, (len(buf) - d) // 4), buf, d))
            out.append(f"    {ename:<24} = {text}\n")
    return "".join(out)


if __name__ == "__main__":
    data = open(sys.argv[1], "rb").read()
    text = fex(data)
    if len(sys.argv) > 2:
        open(sys.argv[2], "w").write(text)
        print(f"wrote {sys.argv[2]} ({text.count(chr(10))} lines)")
    else:
        sys.stdout.write(text)
