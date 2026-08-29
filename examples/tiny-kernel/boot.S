/* Multiboot v1 entry stub. GRUB/QEMU -kernel loads this, jumps to _start. */
.set MB_MAGIC,    0x1BADB002
.set MB_FLAGS,    0x0
.set MB_CHECKSUM, -(MB_MAGIC + MB_FLAGS)

.section .multiboot, "a"
.align 4
.long MB_MAGIC
.long MB_FLAGS
.long MB_CHECKSUM

.section .bss
.align 16
stack_bottom:
.skip 16384
stack_top:

.section .text
.global _start
.type _start, @function
_start:
    mov $stack_top, %esp
    call kmain
    cli
.Lhang:
    hlt
    jmp .Lhang
.size _start, . - _start
