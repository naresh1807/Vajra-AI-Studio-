# Build kernel.elf with LLVM (no cross-gcc, no make needed).
$ErrorActionPreference = 'Stop'
$llvm = if ($env:LLVM) { $env:LLVM } else { 'C:\Program Files\LLVM\bin' }
$cc = Join-Path $llvm 'clang.exe'
$ld = Join-Path $llvm 'ld.lld.exe'
$cflags = @('--target=i386-unknown-none-elf','-m32','-ffreestanding','-nostdlib',
            '-fno-pic','-fno-stack-protector','-O2','-Wall','-Wextra')

Push-Location $PSScriptRoot
try {
  & $cc @cflags -c boot.S   -o boot.o
  & $cc @cflags -c kernel.c -o kernel.o
  & $ld -m elf_i386 -n -T linker.ld -o kernel.elf boot.o kernel.o
  Write-Host 'built kernel.elf'
} finally { Pop-Location }
