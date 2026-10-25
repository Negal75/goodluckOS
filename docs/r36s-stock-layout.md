# GamiJa R36S stock card layout — measured findings

Derived from a real stock dump: 9.53 GiB image (`r36s-no-games-10gb.img`),
analysed 2025 with `image/tools/analyze-gaminja-dump.py`,
`image/tools/scriptbin2fex.py` and `image/tools/identify-file.py`.
**Everything below is measured fact, not inference, and should be posted
to [issue #99](https://github.com/CodeZombie/goodluckOS/issues/99).**

## 1. Partition layout (GPT)

Raw area before the GPT partitions holds the sunxi bootloader chain:

| Region | Location | Content |
| --- | --- | --- |
| boot0 | sector 16 (`eGON.BT0` @ byte 8192) | sunxi BT0 |
| u-boot | ~byte 16.3 MiB (Android Bootloader Interface strings) | sunxi u-boot (Android BSP lineage) |
| **script.bin** | **byte 20488192, sector 40016** | 42900 bytes, 84 sections |

GPT partitions (LBA 1 header, entries at LBA 2):

| # | Label | Sectors | Size | Content |
| --- | --- | --- | --- | --- |
| 1 | `boot-res` | 41984..50175 | 4 MiB | FAT16: `bootlogo.bmp`, `bat/*.bmp` (charging screen), **`magic.bin`** |
| 2 | `env` | 50176..50687 | 256 KiB | raw u-boot env (see §3) |
| 3 | `boot` | 50688..67071 | 8 MiB | FAT: **`uImage` + `uInitrd`** (the stock kernel & ramdisk) |
| 4 | `emusystem` | 67072..5309951 | 2.5 GiB | emulation system |
| 5 | `rootfs` | 5309952..7407103 | 1 GiB | rootfs (`/dev/mmcblk0p5`) |
| 6 | `rootfs_data` | 7407104..11601407 | 2 GiB | writable overlay (`/dev/mmcblk0p6`) |
| 7 | `GAMES` | 11601920..19990527 | 4 GiB | game storage |

`magic.bin` is **not** a script.bin and not a container: it is 512 bytes
of ASCII "GUID" strings (SHA-256
`14d309c67afd6c7a6ce3c580c401162266998385dcf4b06d48dd2d5169ad0eb1`).
Most likely a firmware marker/serial blob used by the vendor's updater.
Irrelevant for booting.

## 2. Stock kernel

- p3/`boot`/`uImage`: **"ARM OpenWrt Linux-3.4.39"**, 3,723,056 bytes,
  load/entry `0x40008000`, uncompressed. (sunxi 3.4 Android-BSP kernel —
  script.bin-parameterised, **no device tree**.)
- p3/`boot`/`uInitrd`: 1,905,216 bytes, load 0.
- The base firmware is **OpenWrt**, not Batocera — "Batocera clone" refers
  to the UI/experience only.

## 3. Boot flow (from the `env` partition, plain text)

```
bootcmd=run setargs_nand boot_normal
console=ttyS0,115200
emusystem=/dev/mmcblk0p4
userdata=/dev/mmcblk0p6
mmc_root=/dev/mmcblk0p5
boot_partition=boot
boot_normal=fatload sunxi_flash ${boot_partition} 40007fc0 uImage; \
            fatload sunxi_flash boot 48000000 uInitrd; \
            bootm 40007fc0 48000000
boot_recovery=fatload sunxi_flash recovery 43800000 uImage;bootm 43800000
```

**The stock bootloader loads the kernel from a FAT FILE
(`boot_partition=boot` → p3/uImage), not from a fixed sector.**
Consequences for goodluckOS:

1. The GA36-MB fixed-offset merge model (browser builder splice at
   sector 172032) **does not apply** to these cards.
2. A GamiJa install instead = keep stock boot0/u-boot/script.bin + GPT,
   then swap the *files*: `p3/uImage` ← goodluckOS mainline kernel
   (uImage with appended DTB — this u-boot's `bootm` passes no DTB), and
   repurpose/replace the rootfs partition (p5/p4) with goodluckOS'.
   The `env` partition's `setargs_*` set `root=/dev/mmcblk0p5`.
3. `GAMINJA_KERNEL_SECTOR` / `BOOT_SECTOR` base-image plumbing is not
   the right mechanism for this layout; the DTB/panel work carries over
   unchanged.

## 4. script.bin — verified extract

- Location: byte 20488192 (sector 40016), length 42900.
- SHA-256: `1b78d3d55823076eaee7bf1bedc419800eee7abe9f834e3401700080371b2193`
- `machine = parrot`, `boot_clock = 1008` (MHz).
- Decoded key sections (full text: `script.fex`):

### Display — panel identity SOLVED

```
[lcd0_para]
    lcd_driver_name = nv3051      <-- NV3051-family, as maintainer suspected
    lcd_x = 640  lcd_y = 480      <-- 640x480, matches upstream NV3051D
    lcd_width = 70  lcd_height = 53
    lcd_dclk_freq = 24 (MHz)      lcd_pwm_ch = 0, freq 50000
    lcd_ht = 820  lcd_hbp = 100  lcd_hspw = 20
    lcd_vt = 510  lcd_vbp = 16  lcd_vspw = 4
    lcd_dsi_if = 0 (non-burst)   lcd_dsi_lane = 4
    lcd_dsi_format = 0 (RGB888)  lcd_dsi_eotp = 0   <-- NO EOT packets
```

`eotp = 0` ⇒ this corresponds to the **`anbernic,rg351v-panel` variant**
(`MIPI_DSI_MODE_NO_EOT_PACKET`) of upstream
`panel-newvision-nv3051d.c` — i.e. our **panel1** DTB. Timing above
(640x480 @ 24 MHz, ht 820/hbp 100/hspw 20/vt 510/vbp 16/vspw 4) can be
cross-checked against the driver's modelines.

### Gamepad — the MCU question ANSWERED

```
[joypad]
    joypad-name = adc_gamepad     <-- ADC-driven analog, NOT an MCU/UART
    amux-count = 4
    amux-channel-mapping = 6 7 5 4   <-- GPADC ch. 6,7 = sticks? 5,4 = triggers?
    button-adc-deadzone = 64 ... poll-interval = 3
    invert-absx = 1  invert-absy = 1
[gpiokey_para]
    key_cnt = 19                  <-- digital buttons via gpio-keys
    key0/key1: code 114/115 (KEY_VOLUMEUP/DOWN)
    keys 304..318 (BTN_TRIGGER_HAPPY1..15), 704, 544..547
```

So mainline needs: `gpio-keys` for 19 buttons + an ADC-joystick driver on
GPADC channels 4/5/6/7 (`sun4i-gpadc-iio` supports A33 GPADC; may need
channel 4-7 enablement). No serial MCU protocol to reverse.

### Power / audio / USB

- PMU on twi1 (i2c1), addr 0x34 (`pmu_twi_addr=52`), battery Rdc 114 mΩ
  (A33 ships AXP-family PMUs; identify exact model from probe later).
- `[audio0] headphone_vol = 59, pa_double_used = 1, headset_mic...` —
  codec + external PA enabled ("pa_double" = speaker path), see full fex.
- `[usbc0] usb_port_type = 0 (peripheral/OTG), usb_host_init_state = 0` —
  explains why the console only enumerates as a gadget and the "OTG to
  PC" attempt showed nothing: stock gadget driver may not be enabled.
- `[wakeup_src_para]`, `[fel_key]` (fel on keys 2..7), `[key_detect_en]`.

## 5. OTG/USB note

Console → phone (TECNO) enumerated and offered USB tethering; console →
PC never enumerates even at the electrical level (`lsusb`/`dmesg`
silent). Suspected half-wired USB-C (CC pins) on the console; not a
blocker — the SD-card-reader route works.

## 7. Installing goodluckOS (file-swap install)

`image/tools/install-gaminja.py` implements the install. Run it on a COPY
of the card image first (or the card itself, only with a separate backup):

```bash
# 1. build the kernel payload (uImage with appended DTB):
docker buildx build --output type=local,dest=kernel/out ./kernel
#    -> kernel/out/uImage_gaminja_a33_panel1 (and _panel2)

# 2. inspect (plan mode, read-only):
./image/tools/install-gaminja.py --target stock-card-copy.img

# 3. install panel1 kernel (retry with panel2 if the screen stays black):
./image/tools/install-gaminja.py --target stock-card-copy.img \
    --uimage kernel/out/uImage_gaminja_a33_panel1 \
    --rootfs-file rootfs/out/images/goodluck_rootfs.img \
    --rootfs-part rootfs --write
```

What it does:

1. **Identity gate** — verifies the card's script.bin at byte 20488192
   against the pinned hash; refuses any other card/revision.
2. **Backs up** the stock p3 `uImage`/`uInitrd` (with SHA-256s) to
   `<target-dir>/gaminja-stock-backup/` before touching anything.
3. **Swaps the boot file** — replaces p3 `uImage` with the goodluckOS
   uImage (FAT12-aware cluster rewrite, byte-exact read-back verified),
   deletes `uInitrd` (not needed; bootcmd drops it).
4. **Rewrites the env partition** (CRC32-checked, u-boot format):
   `bootcmd=fatload sunxi_flash boot 40007fc0 uImage; bootm 40007fc0`,
   `bootargs=console=ttyS0,115200 root=<--root> rootwait rw panic=10`.
   Default `--root` is `/dev/mmcblk0p5` (partition `rootfs`); use
   `--rootfs-part emusystem --root /dev/mmcblk0p4` to target the 2.5 GiB
   partition instead.
5. Optionally writes the rootfs image into the target partition with a
   capacity check.

Recovery: restore the stock `uImage`/`uInitrd` from the backup dir onto
any FAT-mounted copy of the card (e.g. `mcopy`), or re-flash the whole
backup dump. stock env partition is overwritten — keep a full dump.

Regression tests (fully synthetic card, no hardware/dump needed):
`python3 tests/install-gaminja.test.py`.

## 8. Artifacts (kept out of git in `image/out/r36s-analysis/`)

- `layout_report.txt` — analyzer output
- `script_20488192.bin` — extracted script.bin (attach to issue #99)
- `script.fex` — full decoded text (attach to issue #99)
- `magic.bin`, `p2_env.raw` (u-boot env), `p1_boot-res.fat` — evidence
