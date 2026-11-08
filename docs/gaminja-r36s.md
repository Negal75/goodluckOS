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
| Dump analysis tooling | **done** (image/tools/analyze-gaminja-dump.py) |
| Single-file blob identifier (magic.bin, boot.scr, ...) | **done** (image/tools/identify-file.py) |
| script.bin → .fex decoder (offline) | **done** (image/tools/scriptbin2fex.py) |
| Stock layout mapped from a real dump (GPT, boot flow, magic.bin) | **done** — docs/r36s-stock-layout.md |
| Stock bootloader's kernel source | **done** — loads `uImage` from FAT partition p3 (`boot`), **not** a fixed sector |
| NV3051D panel wired into the kernel build | **done** (untested, no hw) |
| Panel identity | **done** — script.bin: `nv3051`, 640x480, 4-lane DSI, **eotp=0 → panel1 variant** |
| GamiJa A33 DTB baseline (panel1 + panel2 variants) | **done** (untested, no hw) |
| Analog stick mechanism | **done (map)** — `adc_gamepad`, 4 GPADC muxes (ch. 4/5/6/7), no MCU; **driver TODO** (BSP amux per-sample switching has no mainline equivalent) |
| Gamepad buttons | **done (map)** — 17 GPIO keys decoded (PG07-13, PL03/04/08-11, PB02/03/06/07) + LRADC volume keys (key_para); PH04/PH05 entries are template junk; wired into `gaminja-r36s.dtsi` |
| Kernel/boot offset of GamiJa stock firmware | **obsolete** — boot is FAT-file based; merge model doesn't apply (docs/r36s-stock-layout.md §3) |
| Matches no approved script.bin hash yet | **two stock hashes measured** (community image `1b78d3d5…`, the unit's shipped card `beaa0cff…91fa`, exact 42,900 bytes) — installer gate goes per-unit (`--expect-scriptbin`) |
| GamiJa install mechanism (swap p3/uImage + env rewrite + rootfs) | **done (tooling)** — image/tools/install-gaminja.py, 15 regression tests |
| Kernel uImage payload (appended-DTB, load 0x40008000) | **done (build)** — kernel/Dockerfile emits `uImage_gaminja_a33_panel1/2` |
| DTB GPIOs vs real PCB | **closed (fex)** — console uart0 PB0/PB1, LEDs PE14/PL02, audio PA PH09, usb1 VBUS PH08, panel reset PH07, PMU on RSB (PL0/PL1); verified only via serial on flash day |
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
  build outputs `uImage_gaminja_a33_panel1/2` + dtbs.

The DTB baseline previously inherited the GA36-MB button/LED/audio map as
a placeholder; it now implements the R36S's own map decoded from
script.bin (gpio-keys on PG/PL/PB pins, LRADC volume, R36S LEDs, uart0
console on PB0/PB1, RSB PMU inherited from GA36-MB). Untested until flash
day — serial console will confirm the PMU/panel probes first. Analog
sticks are still unwired (BSP amux switching has no mainline equivalent).

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

## Real-dump findings (measured — docs/r36s-stock-layout.md)

A device-owner dump has been fully analysed; see
[docs/r36s-stock-layout.md](r36s-stock-layout.md) for the full report.
Headlines:

- GPT layout, 7 labelled partitions; stock kernel is **OpenWrt Linux
  3.4.39** loaded by stock u-boot via **`fatload` from FAT partition
  `boot` (p3)** — a file-based boot, not a fixed sector.
- script.bin confirmed at byte 20488192, SHA-256
  `1b78d3d5…1b2193`; decoded with `scriptbin2fex.py`: panel =
  **nv3051 640x480 4-lane DSI with eotp=0 (→ the panel1/rg351v
  variant)**, analog = **ADC (`adc_gamepad`, GPADC ch. 4/5/6/7)**,
  buttons = 17 GPIO keys (PG/PL/PB banks) + LRADC volume keys,
  PMU on RSB (AXP223, GA36-MB-style PL0/PL1 wiring), console uart0 on
  PB0/PB1, machine name `parrot`.
- `magic.bin` = 512-byte ASCII GUID marker blob in `boot-res`; not boot
  data.

This **changes the install model**: for GamiJa cards the fixed-offset
merge flow cannot work. An install instead keeps stock boot0/u-boot +
script.bin and swaps the p3 `uImage` (+ `uInitrd`) file for a goodluckOS
mainline-kernel uImage (appended-DTB build), repurposing p4/p5 for the
rootfs. The DTB/panel/driver work carries over unchanged.

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
3. **Install + flash a test image** (file-swap model, docs/r36s-stock-layout.md §7):
   build `uImage_gaminja_a33_panel1` (kernel/Dockerfile), run
   `image/tools/install-gaminja.py` against a COPY of the stock card
   (script.bin gate + automatic stock backup first), then write the copy
   to the card and boot watching serial (`ttyS0`, 115200, USB TTY). Try
   `panel2` if the display stays black.
4. **Fix the DTB against reality**: panel picked (panel1 vs panel2),
   PMU probe (RSB vs i2c0), LED colours/functions, usb1 VBUS polarity,
   mmc1 usability. Gamepad buttons + volume keys are already wired from
   the fex decode; the analog sticks still need a driver (BSP amux
   switching has no mainline equivalent).
5. **Full image + firmware-builder release once stable.**

## Flash-day diagnostics (2026-11-08)

No serial adapter on the unit, so visibility comes from one binary signal:
the work LED (PE14), plus whatever the panel shows.

| Boot | LED | Screen | Conclusion |
|---|---|---|---|
| DEBUGLED pan.1 | **on**, stays on | boot-res logo frozen | kernel **executes** (gpio-leds reached); no display stack, no console output |
| DEBUGLED pan.2 | on | logo frozen | same — panel variant is not the differentiator |

Consequences:

- u-boot `boot_normal` chain (`fatload uImage; bootm`) works; magic.bin
  (512-byte `boot-res` GUID marker on p1) is not gating the boot chain.
- `console=tty0` in bootargs produces no text because fbcon never
  attaches while the panel probe stays deferred — and `/dev/console`
  only exists once a console driver does. Not "kernel silent", but
  "kernel wedged before any console".
- Current prime suspect: the PMU/AXP223 never probes, so every regulator
  the panel chain needs (`dc1sw` vdd, `eldo2`, backlight rail) never
  registers and DRM/DSI/panel defer forever.

Active instrument: kernel patch
`kernel/patches/0002-axp20x-debugled-off-on-axp-probe.patch` —
`axp20x_device_probe()` clears PE14 after a successful AXP probe
(works for i2c and rsb paths alike). Result meanings on next boot:

- LED **off after a few seconds** → PMU probed on RSB (or wherever);
  the failure is lower (panel/DSI/regulators) — next: panel flags,
  reset polarity.
- LED **on forever** → PMU never probed; next: PMU-on-i2c0 variant
  (`pmu1_para`: `pmu_twi_addr=52`, `pmu_twi_id=1` in script.fex)
  before conceding to a serial adapter.

Wait ~10–20 s before reading the LED; the LED itself (gpio-leds) will
have turned it on within the first second, the AXP probe happens later.

## Open questions (anyone with a unit can help)

- How do the analog sticks behave with mainline `sun4i-gpadc-iio`
  (channels 0-3 vs the fex's amux indices 4-7)? Determines whether a
  small `adc-joystick`/`gpio-keys-polled` glue driver is needed.
- Is the PMU reachable on i2c0 @0x34 too (fex `[pmu_twi_addr]=52`,
  `[twi_para]` boot bus), or RSB-only like the GA36-MB?
- What are the LED colours for work_led (PE14) / bat_led (PL02)?
- Is the mmc1 SDIO bus wired to anything on the PCB (no wifi in the
  stock config)?

Record answers in [issue #99](https://github.com/CodeZombie/goodluckOS/issues/99).
