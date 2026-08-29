#!/bin/sh
# Build kernel.elf with LLVM (no cross-gcc, no make needed).
set -e
: "${LLVM:=/c/Program Files/LLVM/bin}"
CC="$LLVM/clang"
LD="$LLVM/ld.lld"
TARGET=i386-unknown-none-elf
CFLAGS="--target=$TARGET -m32 -ffreestanding -nostdlib -fno-pic -fno-stack-protector -O2 -Wall -Wextra"

"$CC" $CFLAGS -c boot.S   -o boot.o
"$CC" $CFLAGS -c kernel.c -o kernel.o
"$LD" -m elf_i386 -n -T linker.ld -o kernel.elf boot.o kernel.o
echo "built kernel.elf"
