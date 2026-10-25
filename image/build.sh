#!/bin/bash

mkdir -p ./staging

cp ../kernel/out/android_boot_a23_panel1.img ./staging/
cp ../kernel/out/android_boot_a23_panel2.img ./staging/
cp ../kernel/out/android_boot_a33_panel1.img ./staging/
cp ../kernel/out/android_boot_a33_panel2.img ./staging/
cp ../rootfs/out/images/rootfs.tar ./staging/
cp ../home/out/home.tar ./staging/

mkdir -p out

GAMINJA_BUILD_ARGS=""
if [ -n "${GAMINJA_KERNEL_SECTOR:-}" ]; then
    # GamiJa R36S (Batocera clone) support, issue #99.
    #
    # The GamiJa stock layout boots the kernel from a different offset than
    # the GA36-MB, so building a bootable GamiJa base image requires the
    # measured kernel sector of a real stock card. Until a stock dump has
    # been fully mapped with image/tools/analyze-gaminja-dump.py, do NOT
    # set this variable: a guessed offset will produce an image that boots
    # nothing (or worse).
    #
    # Usage: GAMINJA_KERNEL_SECTOR=<measured sector> ./build.sh
    #
    if ! [[ "${GAMINJA_KERNEL_SECTOR}" =~ ^[0-9]+$ ]] || [ "${GAMINJA_KERNEL_SECTOR}" -lt 1025 ] || [ "${GAMINJA_KERNEL_SECTOR}" -ge 262144 ]; then
        echo "Error: GAMINJA_KERNEL_SECTOR must be between sectors 1025 and 262143 (got: ${GAMINJA_KERNEL_SECTOR})." >&2
        exit 1
    fi
    echo "Building GamiJa R36S base images with kernel at sector ${GAMINJA_KERNEL_SECTOR} (issue #99)."
    GAMINJA_BUILD_ARGS="--build-arg BOOT_SECTOR=${GAMINJA_KERNEL_SECTOR}"
    cp ../kernel/out/android_boot_gaminja_a33_panel1.img ./staging/
    cp ../kernel/out/android_boot_gaminja_a33_panel2.img ./staging/
else
    echo "Skipping GamiJa R36S base images: set GAMINJA_KERNEL_SECTOR to enable (see docs/gaminja-r36s.md)."
fi

if command -v podman &> /dev/null; then
    podman build --build-arg VARIANT=a23_panel1 -o ./out .
    podman build --build-arg VARIANT=a23_panel2 -o ./out .
    podman build --build-arg VARIANT=a33_panel1 -o ./out .
    podman build --build-arg VARIANT=a33_panel2 -o ./out .
    if [ -n "${GAMINJA_BUILD_ARGS}" ]; then
        podman build ${GAMINJA_BUILD_ARGS} --build-arg VARIANT=gaminja_a33_panel1 -o ./out .
        podman build ${GAMINJA_BUILD_ARGS} --build-arg VARIANT=gaminja_a33_panel2 -o ./out .
    fi
elif command -v docker &> /dev/null; then
    docker buildx build --build-arg VARIANT=a23_panel1 --output type=local,dest=./out .
    docker buildx build --build-arg VARIANT=a23_panel2 --output type=local,dest=./out .
    docker buildx build --build-arg VARIANT=a33_panel1 --output type=local,dest=./out .
    docker buildx build --build-arg VARIANT=a33_panel2 --output type=local,dest=./out .
    if [ -n "${GAMINJA_BUILD_ARGS}" ]; then
        docker buildx build ${GAMINJA_BUILD_ARGS} --build-arg VARIANT=gaminja_a33_panel1 --output type=local,dest=./out .
        docker buildx build ${GAMINJA_BUILD_ARGS} --build-arg VARIANT=gaminja_a33_panel2 --output type=local,dest=./out .
    fi
else
    echo "Error: Neither podman nor docker was found in your PATH." >&2
    exit 1
fi
echo "Done"
