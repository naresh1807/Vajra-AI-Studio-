ENTRY(_start)

SECTIONS {
    . = 1M;                          /* multiboot kernels load at 1 MiB */

    .text : ALIGN(0x1000) {
        *(.multiboot)                /* header must be in the first 8 KiB */
        *(.text)
    }
    .rodata : ALIGN(0x1000) { *(.rodata) }
    .data   : ALIGN(0x1000) { *(.data) }
    .bss    : ALIGN(0x1000) { *(COMMON) *(.bss) }
}
