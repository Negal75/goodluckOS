# GamiJa R36S (Batocera clone) Port

This document tracks the work to bring goodluckOS to the **GamiJa R36S**,
a Batocera-firmware clone of the GA36-MB family.

Everything below comes from [issue #99](https://github.com/CodeZombie/goodluckOS/issues/99).
Think of this file as the master checklist for that port; update it as each
item lands or gets disproven.

## Status

| Step | Status |
| --- | --- |
| Firmware builder recognizes the GamiJa stock layout (script.bin probe + scan + layout report) | **done** (docs/download.html) |
| Builder auto-detects the stock kernel offset ("ANDROID!" scan) and logs the suggested `GAMINJA_KERNEL_SECTOR` | **done** (unverified vs real dumps) |
| Dump analysis tooling | **done** (image/tools/analyze-gaminja-dump.py) |
| Single-file blob identifier (magic.bin, boot.scr, ...) | **done** (image/tools/identify-file.py) |
| NV3051D panel wired into the kernel build | **done** (untested, no hw) |
| GamiJa A33 DTB baseline (panel1 + panel2 variants) | **done** (untested, no hw) |
| Kernel/boot offset of GamiJa stock firmware | **open** — needs a mapped stock dump |
| Matches no approved script.bin hash yet | **open** — extract + whitelist |
| Which NV3051D panel variant (panel1 vs panel2) | **open** — try both on hw |
| Gamepad GPIOs / analog-stick MCU | **open** — PCB differs from GA36-MB |
| Audio path (speaker pin, jack return) | **open** |
| GamiJa base images (BOOT_SECTOR-aware) | **done, gated** (`GAMINJA_KERNEL_SECTOR`) |
| Verified flash on real hardware | **not started** |

## What we know (from issue #99)

- The GamiJa hardware uses an **Allwinner A33** (SoC confirmed by the device
  owner; cross-check against the fex when a dump is handy), so A33 is the
  only DTB variant being built — see issue #125 for why RK3326-based
  R36S/Ultra units are out of scope.
- The **PCB is not identical** to the GA36-MB, so a purpose-built `.dtb` is
  required.
- The stock firmware is a **Batocera-like Linux build** with a **different
  bootloader layout** than the GA36-MB stock cards.
- From a real stock dump:
  - `script.bin` lives at **byte 20488192** (GA36-MB: 20340736), i.e.
    sector 40016 vs 39728.
  - The kernel (or boot image) is at a different offset too — exact spot
    **TBD**. This is why goodluckOS cannot boot on these units yet: base
    images must be built with the boot image at the offset the stock
    bootloader actually loads from.
- Device-owner reports indicate the stock SD card **contains a file named
  `magic.bin`** — i.e. part/all of the stock firmware is inside a FAT
  partition that mounts on a PC, not just a raw bootloader area. If the
  stock bootloader loads the kernel from a *file* on that partition
  (u-boot `boot.scr`/extlinux style) rather than a fixed offset, the
  whole offset question may be answered by reading that partition's
  config files directly. See "magic.bin workflow" below.
- The display on the examined unit is an **NV3051**-family panel — the exact
  panel variant is unknown (same "two possible panels, no way to tell" drill
  as the GA36-MB). Upstream Linux ships
  `drivers/gpu/drm/panel/panel-newvision-nv3051d.c` (4-lane DSI, 640x480),
  so panel support needs **no reverse-engineered .ko** for a change. The
  kernel builds both variants — see `kernel/dts/gaminja-r36s.dtsi`.

## Tooling in this repo

### 1. Firmware builder (`docs/download.html`)

Step 1 now probes *all* known layout offsets (GA36-MB and GamiJa) for a
valid `script.bin`, then — if none parse — scans the stock region for any
valid script.bin blob. The builder is fully layout-aware:

- The merge boundary (where the stock bootloader hands over to goodluckOS'
  kernel) comes from the layout table; GA36-MB is sector 172032, GamiJa is
  auto-detected from the first in-bounds `ANDROID!` boot-image header in
  the dump and printed as a suggested `GAMINJA_KERNEL_SECTOR`.
- `KNOWN_HASHES` is layout-agnostic: the moment a GamiJa script.bin hash is
  whitelisted (and its base images are published or built locally with the
  measured sector), the builder unlocks for that layout — no further code
  changes needed.
- Base images are validated against the *stock* card's kernel offset before
  assembling, so a mismatched GA36/GamiJa base cannot be spliced onto the
  wrong card.
- For unrecognized layouts it disables image assembly (refuses to build,
  to protect your hardware) and offers two downloads:

- **your script.bin** — the correctly extracted, hash-verified blob. This
  is what gets whitelisted in `KNOWN_HASHES`.
- **layout report** — partition table, eGON/ANDROID! marker offsets, and
  script.bin probe results. Attach this to issue #99.

### 2. Offline dump analyzer (`image/tools/analyze-gaminja-dump.py`)

Same heuristics, more thorough (mmap-style full scan, section name dump,
extracts payload slices):

```bash
./image/tools/analyze-gaminja-dump.py stock_sdcard.img --extract out/ [--full]
```

Point it at the 60 GB dump from issue #99 (or any GamiJa stock card). It
maps: MBR/GPT, `eGON.BT0` (boot0), `eGON` (boot1/u-boot), `ANDROID!`
boot images, uImage headers, and script.bin candidates — with byte, sector,
and MiB offsets so `dd` commands can be written straight from the report.

### 3. Kernel

- `kernel/dts/gaminja-r36s.dtsi` — shared baseline (panel skeleton + TODO list).
- `kernel/dts/gaminja-r36s-a33-panel1.dts` / `-panel2.dts` — the two
  NV3051D panel variants (they differ only in DSI mode_flags). Flash
  whichever matches the unit's panel; just like the GA36-MB, try both if
  one gives a black screen.
- `CONFIG_DRM_PANEL_NEWVISION_NV3051D` is enabled in `kernel/Dockerfile`;
  build outputs `android_boot_gaminja_a33_panel1/2.img` + dtbs.

The DTB baseline inherits the GA36-MB button/LED/audio map on purpose: it is
the fastest way to get a kernel the LCD and serial console work on, then
diff real hardware against it. Do not trust the inputs until verified.

### 4. Boot offset-aware base images

`image/build.sh` builds `goodluck_base_gaminja_a33_panel1.img` /
`goodluck_base_gaminja_a33_panel2.img` **only** when you explicitly pass the
measured kernel sector:

```bash
GAMINJA_KERNEL_SECTOR=<measured sector> ./build.sh
```

Learned-lesson guard rails: the offset must be inside sectors 1025..262143
(i.e., below the 128 MiB linux partition) or the build fails; the same rule
is enforced inside `image/Dockerfile`.

### 3. Single-file identifier (`image/tools/identify-file.py`)

The observed GamiJa cards mount with **visible files** (`magic.bin` etc.),
so the most direct route to the kernel offset may be reading the card's
boot config files rather than carving raw sectors. Feed the tool *any*
file copied off the card:

```bash
./image/tools/identify-file.py magic.bin
./image/tools/identify-file.py boot.scr          # dumps the embedded script
./image/tools/identify-file.py uImage --extract out/
```

It auto-detects and decodes: sunxi `script.bin` (same parser as the
builder), plain-text `.fex` (prints SoC/LCD/button config directly — gold
for the device tree), `ANDROID!` boot images, u-boot `uImage` (including
`boot.scr` Script images, whose command text usually names the kernel file
and its load address), FIT/DTB blobs, squashfs/ext filesystem images, and
boot0/boot1 stages. Unknown files get entropy stats + hexdump + strings,
ready to attach to issue #99.

**Run it on every small file from the mounted card** (`ls -laR /media/...`,
copy off everything not obviously ROM data). If `boot.scr`/`extlinux.conf`
shows the kernel being loaded *from a file on the FAT partition*, the
fixed-offset merge model (and `GAMINJA_KERNEL_SECTOR`) may be the wrong
approach entirely for these units, and support would instead mean
replacing that file — a much simpler and safer flashing path.

## magic.bin workflow (device owner with the stock card)

1. **Inventory the card** while it is mounted (`/media/...` below is the
   mount point — adjust):
   ```bash
   ls -laR /media/username/PARTITION > card-inventory.txt
   ```
2. **Copy off the small files** (configs, boot scripts, blobs — NOT the
   big ROM assets):
   ```bash
   mkdir card-files
   # copy anything small: magic.bin, boot.scr, extlinux.conf, uEnv.txt,
   # *.ini, *.txt, first few MiB of any small *.img/*.bin
   ```
3. **Identify each one:**
   ```bash
   for f in card-files/*; do
     ./image/tools/identify-file.py "$f" | tee "$f.identified"
   done
   ```
4. **Report**: attach `card-inventory.txt`, each `.identified` output, and
   the extracted `script.bin` hash (or the file itself) to
   [issue #99](https://github.com/CodeZombie/goodluckOS/issues/99).

What each result means for the port plan:

| Identification | Impact |
| --- | --- |
| `magic.bin` = valid `script.bin` | Straightforward: extract, whitelist, verify offset story |
| `magic.bin` = `boot.scr`-style uImage | The script body names the kernel file/offset — port gets much easier |
| `magic.bin` = `fex` text | Direct SoC/LCD/button config for the device tree |
| `magic.bin` = encrypted/magic blob | Extract & post; we reverse the container format |



1. **Inventory + identify the mounted card's files** (magic.bin workflow
   above), and run the analyzer on the full dump. Add the findings to the
   table above. Identify which image the stock bootloader actually loads
   (`eGON` chain, `ANDROID!`, FIT/extlinux/Batocera loader assets, or a
   kernel file on the FAT partition).
2. **Whitelist the script.bin.** Extract via builder or analyzer, compute
   SHA-256, add an entry to `KNOWN_HASHES` in docs/download.html, and (with
   hardware on hand) mark `supported: true`.
3. **Build + flash a test image.** Kernel first via
   `dd if=android_boot_gaminja_a33_panel1.img bs=512 seek=<measured sector> of=/dev/sdX
   conv=notrunc` onto the untouched stock card, watching the serial console
   (`USB TTY`). Try `panel2` if the display stays black.
4. **Fix the DTB against reality**: panel picked (panel1 vs panel2),
   gamepad GPIOs + analog MCU protocol, LEDs, LRADC volume keys, audio.
5. **Full image + firmware-builder release once stable.**

## Open questions (anyone with a unit can help)

- Does the GamiJa use the same GA36-MB gamepad-MCU-over-UART trick, or
  button-driven analog on the SoC/LRADC?
- Which AXP pmic variants are on the GamiJa PCB?
- Is the second TF slot wired to mmc1?
- Do these units ship different display panels per batch (like GA36-MB)?

Record answers in [issue #99](https://github.com/CodeZombie/goodluckOS/issues/99).
