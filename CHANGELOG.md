## [UNRELEASED]
### Added
- GamiJa R36S (Batocera clone) groundwork, tracked in [issue #99](https://github.com/CodeZombie/goodluckOS/issues/99):
  - Firmware builder is fully layout-aware: per-layout script.bin probes (GamiJa at byte 20488192) with dump-wide scan fallback, per-layout merge/kernel offset (GA36-MB stays sector 172032; GamiJa is auto-detected from "ANDROID!" headers and reported as a suggested GAMINJA_KERNEL_SECTOR), base-image validation against the stock card's offset, and a downloadable layout report (MBR/GPT, eGON/ANDROID! markers). It still refuses to assemble images for unverified/unknown layouts.
  - `image/tools/analyze-gaminja-dump.py`: offline stock-dump analyzer (partitions, bootloader markers, script.bin candidates + extraction).
  - `image/tools/identify-file.py`: universal single-file blob identifier for mounted stock cards (script.bin, .fex, ANDROID! boot image, uImage/boot.scr with script-body dump, DTB/FIT, filesystem images, unknown-blob forensics).
  - `image/tools/scriptbin2fex.py`: offline script.bin → .fex decoder (no sunxi-fexc needed).
  - `image/tools/install-gaminja.py`: GamiJa R36S file-swap installer — verifies the card's script.bin against the pinned stock hash, backs up the stock p3 uImage/uInitrd, swaps in the goodluckOS uImage (FAT12-aware, byte-exact read-back verified), rewrites the u-boot env partition (CRC-checked) and optionally writes the rootfs into a target partition. Regression-tested against a fully synthetic card (`tests/install-gaminja.test.py`).
  - Real stock-dump findings (docs/r36s-stock-layout.md): GPT layout with labelled partitions; stock u-boot loads the kernel from a FAT file (`boot` partition), so GamiJa installs are file swaps, not offset merges; stock kernel is OpenWrt Linux 3.4.39; panel = nv3051 640x480 4-lane DSI eotp=0 (panel1 variant); analog = ADC (GPADC ch. 4/5/6/7, no MCU); 17 GPIO buttons + LRADC volume keys; PMU on RSB (AXP223); console uart0 on PB0/PB1.
  - `image/tools/scriptbin2fex.py` GPIO decode corrected: fex GPIO values are six u32 words (port, pin, mux, pull, drv, data) — port bank index 12 = PL/R_PIO. The first decode pass had silently rendered every key with pin 00.
  - `kernel/dts/gaminja-r36s.dtsi` now implements the evidence-based R36S board: gpio-keys on the decoded pins (GA36-MB serial-gamepad/uart1/uart2 dropped), LRADC volume keys kept, R36S LEDs (PE14/PL02) replacing the GA36-MB ones (which collided with buttons), console uart0 on PB0/PB1 as ttyS0, OTG forced peripheral, usb1 VBUS regulator on PH08, mmc0/1 card-detect, panel 1.8 V eldo2 rail, dldo3 = 2.8 V, backlight period per fex.
  - `kernel/Dockerfile` now emits `uImage_gaminja_a33_panel1/2` (appended-DTB zImage wrapped as a legacy u-boot uImage, load/entry 0x40008000 matching the stock env) instead of Android boot images for the GamiJa path.
  - GamiJa A33 DTB baselines (panel1/panel2 variants, screen model unknown) + upstream NV3051D panel driver enabled (`gaminja-r36s.dtsi`, `kernel/Dockerfile`).
  - Boot offset-aware base images: `image/Dockerfile` gained `BOOT_SECTOR`; GamiJa variants build only when `GAMINJA_KERNEL_SECTOR` is set to a verified offset.
  - `docs/gaminja-r36s.md`: master checklist for the port.

## [0.1.0]  - 2026-10-10
### Added
- USB MTP
- TF-2 SUPPORT
- A23 Support
- Panel 2 Support
- Appd/Appctl for much better application management
- Evsieve for interacting with TUI/keyboard applications with the gamepad
- Several terminal applications accessible via Puppy
- Repeat-keys in Puppy
- Credits application
- 

### Changed
- Coupled Puppy's application launch behaviour to appctl instead of the OS itself.
- Fixed some button behaviour in Retroarch
- 

## [0.0.1] - 2026-09-26
- Initial release
