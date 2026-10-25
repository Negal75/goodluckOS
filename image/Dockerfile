# syntax=docker/dockerfile:1
FROM debian:bookworm-slim AS builder

ENV LIBGUESTFS_BACKEND=direct

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    parted \
    libguestfs-tools \
    qemu-system-x86 \
    linux-image-amd64 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

ARG VARIANT

# Sector (512-byte units) where the android boot image lives.
#
# GA36-MB stock cards boot their kernel from sector 172032 (84 MiB). The
# GamiJa R36S (Batocera clone, issue #99) uses a different layout, so its
# build must pass the measured kernel sector via BOOT_SECTOR instead. Until
# a stock GamiJa dump has been fully mapped (docs/gaminja-r36s.md), only
# 172032 is known to be safe.
ARG BOOT_SECTOR=172032

RUN truncate -s 1G "goodluck_${VARIANT}.img" && \
    parted -a optimal -s "goodluck_${VARIANT}.img" \
    mklabel msdos \
    mkpart primary ext4 128MiB 512MiB \
    mkpart primary fat32 512MiB 100%

RUN dd if=/dev/zero of="goodluck_${VARIANT}.img" bs=512 skip=1 seek=1 count=262143 conv=notrunc

COPY "staging/android_boot_${VARIANT}.img" ./
# Guard: a kernel pushed at/inside the linux partition (start 128MiB =
# sector 262144) would get overwritten by rootfs content (or vice versa).
# If the measured GamiJa kernel offset lands there, the partition layout in
# this Dockerfile must be re-worked first.
RUN test ${BOOT_SECTOR} -lt 262144 -a ${BOOT_SECTOR} -gt 1024 || (echo "BOOT_SECTOR must be between sectors 1024 and 262143 (outside both partitions) but is ${BOOT_SECTOR}" && false)
RUN dd if="android_boot_${VARIANT}.img" of="goodluck_${VARIANT}.img" bs=512 seek=${BOOT_SECTOR} conv=notrunc

COPY staging/rootfs.tar ./
RUN guestfish -a "goodluck_${VARIANT}.img" <<EOF
run
mkfs-opts ext4 /dev/sda1 label:linux
mount /dev/sda1 /
tar-in rootfs.tar /
umount /
EOF

COPY staging/home.tar ./
RUN guestfish -a "goodluck_${VARIANT}.img" <<EOF
run
mkfs-opts vfat /dev/sda2 label:HOME
mount /dev/sda2 /
tar-in home.tar /
umount /
EOF

# # Inject custom bootlogo
# COPY res/goodluck_bootlogo.bmp ./goodluck_bootlogo.bmp
# RUN guestfish -a goodluck_$VARIANT.img <<EOF
# run
# mount-vfs "offset=37748736" "vfat" /dev/sda /
# upload goodluck_bootlogo.bmp /bootlogo.bmp
# umount /
# EOF

#######
# A23 #
#######
# RUN truncate -s 1G goodluck_a23.img && \
#     parted -a optimal -s goodluck_a23.img \
#     mklabel msdos \
#     mkpart primary ext4 128MiB 512MiB \
#     mkpart primary fat32 512MiB 100%
#
# # COPY sdcard.img ./
# RUN dd if=/dev/zero of=goodluck_a23.img bs=512 skip=1 seek=1 count=262143 conv=notrunc
#
# COPY staging/android_boot_a23.img ./
# RUN dd if=android_boot_a23.img of=goodluck_a23.img bs=512 seek=172032 conv=notrunc
#
# COPY staging/rootfs.tar ./
# RUN guestfish -a goodluck_a23.img <<EOF
# run
# mkfs-opts ext4 /dev/sda1 label:linux
# mount /dev/sda1 /
# tar-in rootfs.tar /
# umount /
# EOF
#
# COPY staging/home.tar ./
# RUN guestfish -a goodluck_a23.img <<EOF
# run
# mkfs-opts vfat /dev/sda2 label:HOME
# mount /dev/sda2 /
# tar-in home.tar /
# umount /
# EOF

# # Inject custom bootlogo
# COPY res/goodluck_bootlogo.bmp ./goodluck_bootlogo.bmp
# RUN guestfish -a goodluck_a23.img <<EOF
# run
# mount-vfs "offset=37748736" "vfat" /dev/sda /
# upload goodluck_bootlogo.bmp /bootlogo.bmp
# umount /
# EOF

FROM scratch AS export
ARG VARIANT
COPY --from=builder "/workspace/goodluck_${VARIANT}.img" "/goodluck_base_${VARIANT}.img"
#COPY --from=builder /workspace/goodluck_a23.img /goodluck_base_a23.img
