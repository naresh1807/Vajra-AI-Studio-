# tiny-kernel

A ~40-line freestanding multiboot kernel used to exercise Vajra's OS-development
agent (manual v3.0 Phase 9) end to end: build with the toolchain, boot under
QEMU, read the serial log, confirm the ready marker.

On boot it brings up COM1 and prints:

```
VAJRA-KERNEL-OK: booted via multiboot, serial online
```

## Build + run by hand

```sh
make                       # -> kernel.elf  (LLVM clang + ld.lld, no cross-gcc)
make run                   # qemu-system-i386 -kernel kernel.elf -nographic ...
```

## Build + run via the OS-dev agent

With the Core running:

```
POST /api/osdev/run
{ "instruction": "Build the kernel in examples/tiny-kernel with `make`, then boot
   kernel.elf with osdev_boot (arch i386, ready_marker \"VAJRA-KERNEL-OK\").
   Report the serial line." }
```

## Files

- `boot.S` — multiboot header + `_start` (sets stack, calls `kmain`, halts)
- `kernel.c` — 16550 UART init + `serial_puts`
- `linker.ld` — load at 1 MiB; link with `-n` so the multiboot header lands in
  the first 8 KiB of the file (QEMU's loader requires that)
- `Makefile`
