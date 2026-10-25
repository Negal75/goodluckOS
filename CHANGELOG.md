## [UNRELEASED]
### Added
- GamiJa R36S (Batocera clone) groundwork, tracked in [issue #99](https://github.com/CodeZombie/goodluckOS/issues/99):
  - Firmware builder now probes GamiJa script.bin offsets (20488192) and scans unknown dumps, produces the correct script.bin hash, generates a bit-for-bit layout report (MBR/GPT, eGON/ANDROID! markers), and refuses to assemble images for layouts it cannot flash safely.
  - `image/tools/analyze-gaminja-dump.py`: offline stock-dump analyzer (partitions, bootloader markers, script.bin candidates + extraction).
  - GamiJa A23/A33 DTB baselines + upstream NV3051D panel driver enabled (`gaminja-r36s.dtsi`, `kernel/Dockerfile`).
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
