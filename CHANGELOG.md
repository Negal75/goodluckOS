## [UNRELEASED]
### Added
- GamiJa R36S (Batocera clone) groundwork, tracked in [issue #99](https://github.com/CodeZombie/goodluckOS/issues/99):
  - Firmware builder is fully layout-aware: per-layout script.bin probes (GamiJa at byte 20488192) with dump-wide scan fallback, per-layout merge/kernel offset (GA36-MB stays sector 172032; GamiJa is auto-detected from "ANDROID!" headers and reported as a suggested GAMINJA_KERNEL_SECTOR), base-image validation against the stock card's offset, and a downloadable layout report (MBR/GPT, eGON/ANDROID! markers). It still refuses to assemble images for unverified/unknown layouts.
  - `image/tools/analyze-gaminja-dump.py`: offline stock-dump analyzer (partitions, bootloader markers, script.bin candidates + extraction).
  - `image/tools/identify-file.py`: universal single-file blob identifier for mounted stock cards (script.bin, .fex, ANDROID! boot image, uImage/boot.scr with script-body dump, DTB/FIT, filesystem images, unknown-blob forensics).
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
