# Tiny freestanding multiboot kernel - builds with LLVM (no cross-gcc needed).
# Boot it:  qemu-system-i386 -kernel kernel.elf -nographic -serial mon:stdio
LLVM ?= C:/Program Files/LLVM/bin
CC   := $(LLVM)/clang
LD   := $(LLVM)/ld.lld
TARGET := i386-unknown-none-elf
CFLAGS := --target=$(TARGET) -m32 -ffreestanding -nostdlib -fno-pic \
          -fno-stack-protector -O2 -Wall -Wextra
LDFLAGS := -m elf_i386 -n -T linker.ld

kernel.elf: boot.o kernel.o linker.ld
	"$(LD)" $(LDFLAGS) -o $@ boot.o kernel.o

boot.o: boot.S
	"$(CC)" $(CFLAGS) -c $< -o $@

kernel.o: kernel.c
	"$(CC)" $(CFLAGS) -c $< -o $@

run: kernel.elf
	qemu-system-i386 -kernel kernel.elf -nographic -serial mon:stdio -no-reboot -nic none

clean:
	rm -f *.o kernel.elf

.PHONY: run clean
