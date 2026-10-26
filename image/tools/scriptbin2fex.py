#!/usr/bin/env python3
"""
scriptbin2fex.py - convert a sunxi script.bin blob to .fex-style text
(offline stand-in for `sunxi-fexc -u`).

Layout (reverse-engineered from real files, cross-checked against
sunxi-tools' script.bin parser):

  header (16 B): u32 section_count, u32 total_len, ...
  section (40 B): name[32], entry_count s32, entry_table_off s32 (words)
  entry   (40 B): name[32], value_off s32 (words), packed u32 = (count<<16)|type

  type 1 = int list (count words), 2 = chars (count*4 B), 5 = chars,
  4 = GPIO (six u32 words: port, pin, mul_sel, pull, drv, data).
           Port is a 1-based bank index (1=PA ... 8=PH, 12=PL on A33);
           0xffff means "not configured".
"""
import struct
import sys

HEADER = 16
STRUCT = 40
PORTS = "ABCDEFGHIJKL"
INVALID_PORT = 0xFFFF


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
            elif vtype == 4:  # GPIO: port, pin, mul_sel, pull, drv, data (u32 words)
                w = struct.unpack_from("<6I", buf, d)
                if len(w) < 6:
                    text = "gpio? " + buf[d : d + 24].hex(" ")
                elif w[0] == INVALID_PORT:
                    text = "disabled"
                elif 1 <= w[0] <= len(PORTS):
                    p = f"P{PORTS[w[0] - 1]}{w[1]:02d}"
                    pull, drv = w[3], w[4]
                    pull_s = "default" if pull in (INVALID_PORT, 0xFFFFFFFF) else str(pull)
                    drv_s = "default" if drv in (INVALID_PORT, 0xFFFFFFFF) else str(drv)
                    text = f"port:{p}<{w[2]}><{pull_s}><{drv_s}><{w[5]}>"
                else:
                    text = "gpio? " + " ".join(f"{v:#x}" for v in w)
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
