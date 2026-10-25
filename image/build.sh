#!/bin/bash

mkdir -p ./staging

cp ../kernel/out/android_boot_a23_panel1.img ./staging/
cp ../kernel/out/android_boot_a23_panel2.img ./staging/
cp ../kernel/out/android_boot_a33_panel1.img ./staging/
cp ../kernel/out/android_boot_a33_panel2.img ./staging/
cp ../rootfs/out/images/rootfs.tar ./staging/
cp ../home/out/home.tar ./staging/

mkdir -p out

# GamiJa R36S (issue #99): NOTE the install model changed after a real
# stock dump was measured (docs/r36s-stock-layout.md). GamiJa cards boot
# the kernel from a FILE (u-boot `fatload` from the FAT partition `boot`),
# so there is no "kernel offset" to bake into a base image, and no GamiJa
# base images are built here. Instead:
#   - kernel/Dockerfile now emits uImage_gaminja_a33_panel1/2
#   - image/tools/install-gaminja.py swaps that uImage into a stock card
#     image and rewrites the env partition.
# GA36-MB base image building below is unchanged.
GAMINJA_BUILD_ARGS=""
if [ -n "${GAMINJA_KERNEL_SECTOR:-}" ]; then
    echo "Error: GAMINJA_KERNEL_SECTOR is obsolete - GamiJa boots via 'fatload' from the FAT" >&2
    echo "partition 'boot'; use image/tools/install-gaminja.py instead (docs/r36s-stock-layout.md)." >&2
    exit 1
fi

if command -v podman &> /dev/null; then
    podman build --build-arg VARIANT=a23_panel1 -o ./out .
    podman build --build-arg VARIANT=a23_panel2 -o ./out .
    podman build --build-arg VARIANT=a33_panel1 -o ./out .
    podman build --build-arg VARIANT=a33_panel2 -o ./out .
elif command -v docker &> /dev/null; then
    docker buildx build --build-arg VARIANT=a23_panel1 --output type=local,dest=./out .
    docker buildx build --build-arg VARIANT=a23_panel2 --output type=local,dest=./out .
    docker buildx build --build-arg VARIANT=a33_panel1 --output type=local,dest=./out .
    docker buildx build --build-arg VARIANT=a33_panel2 --output type=local,dest=./out .
else
    echo "Error: Neither podman nor docker was found in your PATH." >&2
    exit 1
fi
echo "Done"
