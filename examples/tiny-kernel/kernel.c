/* Freestanding: no libc. Bring up COM1 and print a line the OS-dev agent
   (core/osdev/vm.py) recognises as a successful boot. */

static void outb(unsigned short port, unsigned char val) {
    __asm__ volatile("outb %0, %1" : : "a"(val), "Nd"(port));
}
static unsigned char inb(unsigned short port) {
    unsigned char r;
    __asm__ volatile("inb %1, %0" : "=a"(r) : "Nd"(port));
    return r;
}

#define COM1 0x3F8

static void serial_init(void) {
    outb(COM1 + 1, 0x00); /* disable interrupts */
    outb(COM1 + 3, 0x80); /* enable DLAB */
    outb(COM1 + 0, 0x03); /* divisor 3 -> 38400 baud */
    outb(COM1 + 1, 0x00);
    outb(COM1 + 3, 0x03); /* 8N1, DLAB off */
    outb(COM1 + 2, 0xC7); /* FIFO on, clear, 14-byte threshold */
    outb(COM1 + 4, 0x0B); /* IRQs on, RTS/DSR set */
}

static void serial_putc(char c) {
    while ((inb(COM1 + 5) & 0x20) == 0) {
    }
    outb(COM1, (unsigned char)c);
}

static void serial_puts(const char *s) {
    for (; *s; ++s) {
        if (*s == '\n')
            serial_putc('\r');
        serial_putc(*s);
    }
}

void kmain(void) {
    serial_init();
    serial_puts("VAJRA-KERNEL-OK: booted via multiboot, serial online\n");
    for (;;)
        __asm__ volatile("hlt");
}
