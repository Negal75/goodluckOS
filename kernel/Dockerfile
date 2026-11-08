# syntax=docker/dockerfile:1
FROM debian:bookworm-slim AS kernel_builder

RUN apt-get update && apt-get install -y \
    build-essential gcc-arm-linux-gnueabihf binutils-arm-linux-gnueabihf \
    bc bison flex libssl-dev make libc6-dev libncurses5-dev \
    git wget cpio kmod rsync device-tree-compiler mkbootimg u-boot-tools \
    && rm -rf /var/lib/apt/lists/*

ENV ARCH=arm
ENV CROSS_COMPILE=arm-linux-gnueabihf-

WORKDIR /src
RUN git clone --depth=1 -b v7.2.9 https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git

WORKDIR /src/linux

# Retired
# These flags make booting SLOW.
# They're necessary for getting UART output if you have uart soldered up though.
#   FLAGS:
#     ./scripts/config --enable CONFIG_FRAMEBUFFER_CONSOLE && \
#   CMDLINE:
#       earlycon=uart,mmio32,0x01c28800
#       initcall_debug=1

RUN make sunxi_defconfig
RUN ./scripts/config --enable CONFIG_ARM_APPENDED_DTB && \
    ./scripts/config --enable CONFIG_ARM_ATAG_DTB_COMPAT && \
    ./scripts/config --set-str CONFIG_CMDLINE "root=/dev/mmcblk0p1 rootfstype=ext4 rootwait rw init=/sbin/init coherent_pool=4m loglevel=8" && \
    ./scripts/config --enable CONFIG_CMDLINE_FORCE && \
    ./scripts/config --enable CONFIG_EXT4_FS && \
    ./scripts/config --enable CONFIG_DEVTMPFS && \
    ./scripts/config --enable CONFIG_DEVTMPFS_MOUNT && \
    ./scripts/config --enable CONFIG_GPIO_SYSFS && \
    ./scripts/config --enable CONFIG_VFP && \
    ./scripts/config --enable CONFIG_VFPv4 && \
    ./scripts/config --enable CONFIG_NEON && \
    ./scripts/config --enable CONFIG_SMP && \
    ./scripts/config --enable CONFIG_ARCH_SUNXI && \
    ./scripts/config --enable CONFIG_MACH_SUN8I && \
    ./scripts/config --enable CONFIG_PREEMPT && \
    ./scripts/config --enable CONFIG_CPU_FREQ && \
    ./scripts/config --enable CONFIG_CPU_FREQ_DEFAULT_GOV_ONDEMAND && \
    ./scripts/config --enable CONFIG_CC_OPTIMIZE_FOR_PERFORMANCE && \
    ./scripts/config --enable CONFIG_POWER_SUPPLY && \
    ./scripts/config --enable CONFIG_SUNXI_RSB && \
    ./scripts/config --enable CONFIG_MFD_AXP20X && \
    ./scripts/config --enable CONFIG_MFD_AXP20X_RSB && \
    ./scripts/config --enable CONFIG_AXP20X_POWER && \
    ./scripts/config --enable CONFIG_REGULATOR_AXP20X && \
    ./scripts/config --enable CONFIG_BATTERY_AXP20X && \
    ./scripts/config --enable CONFIG_DRM_SUN4I && \
    ./scripts/config --enable CONFIG_DRM_PANEL_SIMPLE && \
    ./scripts/config --enable CONFIG_BACKLIGHT_PWM && \
    ./scripts/config --enable CONFIG_PWM_SUN4I && \
    ./scripts/config --enable CONFIG_SND_SUN8I_CODEC && \
    ./scripts/config --enable CONFIG_DRM_SUN6I_MIPI_DSI && \
    ./scripts/config --enable CONFIG_COMMON_CLK_DEBUGFS && \
    ./scripts/config --enable CONFIG_DRM_MIPI_DSI && \
    ./scripts/config --enable CONFIG_DRM_FBDEV_EMULATION && \
    ./scripts/config --enable CONFIG_FB && \
    ./scripts/config --enable CONFIG_DRM_LIMA && \
    ./scripts/config --enable CONFIG_USB && \
    ./scripts/config --enable CONFIG_USB_EHCI_HCD && \
    ./scripts/config --enable CONFIG_USB_EHCI_HCD_PLATFORM && \
    ./scripts/config --enable CONFIG_USB_OHCI_HCD && \
    ./scripts/config --enable CONFIG_USB_OHCI_HCD_PLATFORM && \
    ./scripts/config --enable CONFIG_USB_MUSB_HDRC && \
    ./scripts/config --enable CONFIG_USB_MUSB_SUNXI && \
    ./scripts/config --enable CONFIG_USB_MUSB_DUAL_ROLE && \
    ./scripts/config --enable CONFIG_PHY_SUN4I_USB && \
    ./scripts/config --enable CONFIG_USB_ANNOUNCE_NEW_DEVICES && \
    ./scripts/config --enable CONFIG_USB_F_ACM && \
    ./scripts/config --enable CONFIG_USB_GADGET && \
    ./scripts/config --enable CONFIG_USB_LIBCOMPOSITE && \
    ./scripts/config --enable CONFIG_USB_CONFIGFS && \
    ./scripts/config --enable CONFIG_USB_CONFIGFS_SERIAL && \
    ./scripts/config --enable CONFIG_USB_CONFIGFS_ACM && \
    ./scripts/config --enable CONFIG_USB_CONFIGFS_F_FS && \
    ./scripts/config --enable CONFIG_POSIX_MQUEUE && \
    ./scripts/config --enable CONFIG_INPUT_KEYBOARD && \
    ./scripts/config --enable CONFIG_KEYBOARD_GPIO && \
    ./scripts/config --enable CONFIG_KEYBOARD_GPIO_POLLED && \
    ./scripts/config --enable CONFIG_INPUT_JOYDEV && \
    ./scripts/config --enable CONFIG_SWAP && \
    ./scripts/config --enable CONFIG_ZSMALLOC && \
    ./scripts/config --enable CONFIG_ZRAM && \
    ./scripts/config --enable CONFIG_CRYPTO_LZ4 && \
    ./scripts/config --enable CONFIG_CRYPTO_ZSTD && \
    ./scripts/config --enable CONFIG_CRYPTO_LZO && \
    ./scripts/config --enable CONFIG_THERMAL && \
    ./scripts/config --enable CONFIG_CPU_THERMAL && \
    ./scripts/config --enable CONFIG_THERMAL_GOV_STEP_WISE && \
    ./scripts/config --enable CONFIG_IIO && \
    ./scripts/config --enable CONFIG_MFD_SUN4I_GPADC && \
    ./scripts/config --enable CONFIG_SUN4I_GPADC && \
    ./scripts/config --enable CONFIG_SUN8I_THERMAL && \
    ./scripts/config --enable CONFIG_SOUND && \
    ./scripts/config --enable CONFIG_SND && \
    ./scripts/config --enable CONFIG_SND_SOC && \
    ./scripts/config --enable CONFIG_SND_SIMPLE_CARD && \
    ./scripts/config --enable CONFIG_SND_SOC_SIMPLE_AMPLIFIER && \
    ./scripts/config --enable CONFIG_SND_SUN4I_CODEC && \
    ./scripts/config --enable CONFIG_SND_SUN8I_CODEC_ANALOG && \
    ./scripts/config --enable CONFIG_KEYBOARD_SUN4I_LRADC && \
    ./scripts/config --enable CONFIG_REGULATOR_FIXED_VOLTAGE && \
    ./scripts/config --enable CONFIG_INPUT_JOYSTICK && \
    ./scripts/config --enable CONFIG_SERIAL_DEV_CTRL_TTYPORT && \
    ./scripts/config --enable CONFIG_SERIAL_DEV_BUS && \
    ./scripts/config --enable CONFIG_MULTIUSER && \
    ./scripts/config --enable CONFIG_NAMESPACES && \
    ./scripts/config --enable CONFIG_USER_NS && \
    ./scripts/config --enable CONFIG_UTS_NS && \
    ./scripts/config --enable CONFIG_SYSVIPC && \
    ./scripts/config --enable CONFIG_IPC_NS && \
    ./scripts/config --enable CONFIG_PID_NS && \
    ./scripts/config --enable CONFIG_NET_NS && \
    ./scripts/config --enable CONFIG_BLK_DEV_LOOP && \
    ./scripts/config --enable CONFIG_SQUASHFS && \
    ./scripts/config --enable CONFIG_SQUASHFS_XZ && \
    ./scripts/config --enable CONFIG_SQUASHFS_ZSTD && \
    ./scripts/config --enable CONFIG_OVERLAY_FS && \
    ./scripts/config --enable CONFIG_INPUT_MISC && \
    ./scripts/config --enable CONFIG_INPUT_UINPUT && \
    ./scripts/config --enable CONFIG_CGROUPS && \
    ./scripts/config --enable CONFIG_EXFAT_FS && \
    ./scripts/config --enable CONFIG_VFAT_FS && \
    ./scripts/config --enable CONFIG_NLS && \
    ./scripts/config --enable CONFIG_NLS_UTF8 && \
    ./scripts/config --set-str CONFIG_EXFAT_DEFAULT_IOCHARSET "utf8" && \
    make olddefconfig

# Build the vanilla kernel - Docker will cache this long step permanently
RUN make -j$(nproc) zImage dtbs

# Fixes to upstream drivers (reset first: the cached base image may already
# carry previously applied patches, and git apply fails on double-apply)
COPY patches/ /src/patches/
RUN cd /src/linux && git checkout -- . && git apply /src/patches/*.patch

# Panel driver
COPY drivers/jd9366-ga36mbv1-2.c drivers/gpu/drm/panel/jd9366-ga36mbv1-2.c
RUN echo 'obj-$(CONFIG_DRM_PANEL_JD9366) += jd9366-ga36mbv1-2.o' >> drivers/gpu/drm/panel/Makefile
RUN sed -i '/^endmenu/i \
config DRM_PANEL_JD9366\n\
\ttristate "JD9366 panel"\n\
\tdepends on OF && DRM && BACKLIGHT_CLASS_DEVICE\n\
\thelp\n\
\t  Say Y here if you want to enable support for JD9366 panels.\n\
' drivers/gpu/drm/panel/Kconfig

# Gamepad driver
COPY drivers/ga36mb-gamepad.c drivers/input/joystick/ga36mb-gamepad.c
RUN echo 'obj-$(CONFIG_GA36MB_GAMEPAD) += ga36mb-gamepad.o' >> drivers/input/joystick/Makefile
RUN sed -i '/^endif/i \
config GA36MB_GAMEPAD\n\
\ttristate "GA36MB GAMEPAD"\n\
\tdepends on SERIAL_DEV_BUS\n\
\thelp\n\
\t  Say Y here to enable support for the GA36-MB Gamepad.\n\
' drivers/input/joystick/Kconfig

COPY dts/ arch/arm/boot/dts/allwinner/
# COPY dts/sun8i-a33-ga36mb.dts arch/arm/boot/dts/allwinner/
# COPY dts/sun8i-a23-ga36mb.dts arch/arm/boot/dts/allwinner/
RUN echo 'dtb-$(CONFIG_MACH_SUN8I) += ga36mb-a23-panel1.dtb ga36mb-a23-panel2.dtb ga36mb-a33-panel1.dtb ga36mb-a33-panel2.dtb\n' >> arch/arm/boot/dts/allwinner/Makefile
RUN echo 'dtb-$(CONFIG_MACH_SUN8I) += gaminja-r36s-a33-panel1.dtb gaminja-r36s-a33-panel2.dtb\n' >> arch/arm/boot/dts/allwinner/Makefile

# Enable the upstream Newvision NV3051D panel driver, which covers GamiJa
# R36S stock panels (issue #99) without needing a reverse-engineered .ko,
# then rebuild once more with the full driver set enabled.
RUN ./scripts/config --enable CONFIG_DRM_PANEL_NEWVISION_NV3051D && \
    ./scripts/config --enable CONFIG_DRM_PANEL_JD9366 && \
    ./scripts/config --enable CONFIG_GA36MB_GAMEPAD && \
    make olddefconfig

RUN make -j$(nproc) zImage dtbs

RUN cat arch/arm/boot/zImage arch/arm/boot/dts/allwinner/ga36mb-a23-panel1.dtb > arch/arm/boot/zImage_with_dtb_a23_panel1
RUN cat arch/arm/boot/zImage arch/arm/boot/dts/allwinner/ga36mb-a23-panel2.dtb > arch/arm/boot/zImage_with_dtb_a23_panel2
RUN cat arch/arm/boot/zImage arch/arm/boot/dts/allwinner/ga36mb-a33-panel1.dtb > arch/arm/boot/zImage_with_dtb_a33_panel1
RUN cat arch/arm/boot/zImage arch/arm/boot/dts/allwinner/ga36mb-a33-panel2.dtb > arch/arm/boot/zImage_with_dtb_a33_panel2

RUN touch empty_ramdisk
RUN mkbootimg \
    --kernel arch/arm/boot/zImage_with_dtb_a23_panel1 \
    --ramdisk empty_ramdisk \
    --base 0x40000000 \
    --board sun8i \
    --pagesize 2048 \
    -o /src/android_boot_a23_panel1.img

RUN mkbootimg \
    --kernel arch/arm/boot/zImage_with_dtb_a23_panel2 \
    --ramdisk empty_ramdisk \
    --base 0x40000000 \
    --board sun8i \
    --pagesize 2048 \
    -o /src/android_boot_a23_panel2.img

RUN mkbootimg \
    --kernel arch/arm/boot/zImage_with_dtb_a33_panel1 \
    --ramdisk empty_ramdisk \
    --base 0x40000000 \
    --board sun8i \
    --pagesize 2048 \
    -o /src/android_boot_a33_panel1.img

RUN mkbootimg \
    --kernel arch/arm/boot/zImage_with_dtb_a33_panel2 \
    --ramdisk empty_ramdisk \
    --base 0x40000000 \
    --board sun8i \
    --pagesize 2048 \
    -o /src/android_boot_a33_panel2.img

# GamiJa R36S boot payload (issue #99, measured boot flow). The stock
# GamiJa u-boot loads the kernel from a FILE, not a fixed sector:
#   boot_normal=fatload sunxi_flash boot 40007fc0 uImage; \
#               fatload sunxi_flash boot 48000000 uInitrd; \
#               bootm 40007fc0 48000000
# So ship a legacy u-boot uImage wrapping the appended-DTB zImage (this
# u-boot's `bootm` passes no DTB, hence the appended one; ATAG bootargs
# from the env partition reach the kernel via CONFIG_ARM_ATAG_DTB_COMPAT).
# Load/entry 0x40008000 matches the stock env; the installer fatloads the
# uImage to 0x40007fc0 so the header sits 0x40 below, like stock.
RUN cat arch/arm/boot/zImage arch/arm/boot/dts/allwinner/gaminja-r36s-a33-panel1.dtb > arch/arm/boot/zImage_with_dtb_gaminja_a33_panel1
RUN cat arch/arm/boot/zImage arch/arm/boot/dts/allwinner/gaminja-r36s-a33-panel2.dtb > arch/arm/boot/zImage_with_dtb_gaminja_a33_panel2

RUN mkimage -A arm -O linux -T kernel -C none -a 0x40008000 -e 0x40008000 \
    -n "goodluckOS_gaminja_p1" \
    -d arch/arm/boot/zImage_with_dtb_gaminja_a33_panel1 \
    /src/uImage_gaminja_a33_panel1

RUN mkimage -A arm -O linux -T kernel -C none -a 0x40008000 -e 0x40008000 \
    -n "goodluckOS_gaminja_p2" \
    -d arch/arm/boot/zImage_with_dtb_gaminja_a33_panel2 \
    /src/uImage_gaminja_a33_panel2

FROM scratch AS artifacts
COPY --from=kernel_builder /src/android_boot_a23_panel1.img ./android_boot_a23_panel1.img
COPY --from=kernel_builder /src/android_boot_a23_panel2.img ./android_boot_a23_panel2.img
COPY --from=kernel_builder /src/android_boot_a33_panel1.img ./android_boot_a33_panel1.img
COPY --from=kernel_builder /src/android_boot_a33_panel2.img ./android_boot_a33_panel2.img
COPY --from=kernel_builder /src/uImage_gaminja_a33_panel1 ./uImage_gaminja_a33_panel1
COPY --from=kernel_builder /src/uImage_gaminja_a33_panel2 ./uImage_gaminja_a33_panel2
COPY --from=kernel_builder /src/linux/arch/arm/boot/dts/allwinner/ga36mb-a23-panel1.dtb ./dtb/ga36mb-a23-panel1.dtb
COPY --from=kernel_builder /src/linux/arch/arm/boot/dts/allwinner/ga36mb-a23-panel2.dtb ./dtb/ga36mb-a23-panel2.dtb
COPY --from=kernel_builder /src/linux/arch/arm/boot/dts/allwinner/ga36mb-a33-panel1.dtb ./dtb/ga36mb-a33-panel1.dtb
COPY --from=kernel_builder /src/linux/arch/arm/boot/dts/allwinner/ga36mb-a33-panel2.dtb ./dtb/ga36mb-a33-panel2.dtb
COPY --from=kernel_builder /src/linux/arch/arm/boot/dts/allwinner/gaminja-r36s-a33-panel1.dtb ./dtb/gaminja-r36s-a33-panel1.dtb
COPY --from=kernel_builder /src/linux/arch/arm/boot/dts/allwinner/gaminja-r36s-a33-panel2.dtb ./dtb/gaminja-r36s-a33-panel2.dtb
COPY --from=kernel_builder /src/linux/.config ./kernel_config.txt
