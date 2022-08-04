# Asahi Linux installer

This Installer is intended for the currently alpha [Asahi Linux](https://asahilinux.org) distribution, aimed at running Linux on M1 and future Apple Silicon.

Currently working is a command line interface with a GUI version on the way.

## Usage

To use the command line interface, run
```bash
curl https://alx.sh | sh
```

To use the experimental GUI, navigate to the releases and download the .app.zip file, or for latest build go to GUI/Asahi Linux Installer.app.

To build yourself, open GUI/Asahi Linux Installer in Xcode and build.

## Requirements

- M1, M1 Pro, or M1 Max machine (Mac Studio excluded)
- macOS 12.3 or later, logged in as an admin user
- At least 53GB of free disk space (Desktop install)
- You need 15GB for Asahi Linux Desktop, but macOS itself needs a lot of free space for system updates to work, so the installer will expect you to leave 38GB of extra slack in macOS by default to avoid shooting yourself in the foot. For example, if you have 60GB of free space, you will be able to shrink macOS by up to 22GB by default, freeing up 22GB for the new Linux install and leaving 38GB of remaining free space in the macOS partition. If you want to disable this check, enable expert mode when prompted.
- A working internet connection: The installer will download 700MB ~ 4GB of data, depending on the OS you select.
- If you use Time Machine, you may find that you do not have enough free space. This is caused by local Time Machine snapshots taking up the “free” space in your volume. You can learn how to delete these to truly free up space here.

## Process 

First of all, for the full info see the [blog post](https://asahilinux.org/2022/03/asahi-linux-alpha-release/), from where the following information is taken.

The installer is designed to be as self-explanatory as possible. You will see a series of prompts that guide you through resizing your macOS partition (if necessary) and installing your new OS. We expect users to install Linux alongside macOS at this point. The installer will not delete or affect your macOS installation, other than performing a live resize.

Once the first stage of the installation is done, you will have to reboot into 1TR mode (One True recoveryOS) in order to finish the install. Read the instructions that the installer prints carefully! Simply rebooting into the new OS won’t work until this is done. You need to fully shut down your machine, then boot by holding down the power button until you see “Entering startup options”, choose your new OS in the boot selector menu, and follow the prompts.

The installer provides these OS options:

**Asahi Linux Desktop**

A customized remix of Arch Linux ARM that comes with a full Plasma desktop and all the basic packages to get you started with a desktop environment. It includes a graphical first-boot set-up wizard, so you won’t have to dig around to change your settings or create your first user. No root password by default; use sudo to become root.

**Asahi Linux Minimal (Arch Linux ARM)**

A vanilla Arch Linux ARM environment, with only the minimal support packages to integrate with the boot process and hardware on Apple Silicon machines. Arch users will feel right at home!

Log in as root/root or alarm/alarm. Don’t forget to change both passwords! SSH is disabled by default for security reasons, so you’ll have to enable it manually.

**UEFI environment only (m1n1 + U-Boot + ESP)**

No distribution, just a minimal UEFI boot environment. With this, you can boot an OS installer from a USB drive and install whatever you want (as long as it supports these machines, of course)!


## What works

All M1, M1 Pro, and M1 Max devices are supported except for the Mac Studio.

- Wi-Fi
- USB2 (Thunderbolt ports)
- USB3 (Mac Mini Type A ports)
- Screen (no GPU)
- NVMe
- Lid switch
- Power button
- Built-in display (framebuffer only)
- Built-in keyboard/touchpad
- Display backlight on/off
- Battery information / charge control
- RTC
- Ethernet (desktops)
- SD card reader (M1 Pro/Max)
- CPU frequency switching


M1 machines only (no Pro/Max):

- Headphones jack (might be flaky)

Mac Mini only:

- HDMI output

Not yet, but coming soon:

- USB3
- Speakers
- Display controller (backlight brightness control, V-Sync, proper DPMS)

## What doesn’t work:

Everything else, but notably:

- DisplayPort
- Thunderbolt
- HDMI on the MacBooks
- Bluetooth
- GPU acceleration
- Video codec acceleration
- Neural Engine
- CPU deep idle
- Sleep mode
- Camera
- Touch Bar
  - Note: on the 13" MacBook Pro, you can use Fn + the number row keys (1-9, 0, and the next two) as F1..F12 in lieu of the Touch Bar.

## Known bugs

- If Wi-Fi doesn’t work, try toggling it off and on in the network management menu
- If the headphones jack doesn’t work or only one channel works, try rebooting. There’s a flakiness issue.

## Known broken applications

The Asahi Linux kernel is compiled to use 16K pages. This both performs better, and is required with our kernel branch right now in order to work properly with the M1’s IOMMUs. Unfortunately, some Linux software has problems running with 16K pages. Most notably:

- Emacs (fix committed, not released)
- Anything using jemalloc (e.g. Rust installed via the official Arch repositories)
- Anything using libunwind (fix committed, not released)

Hopefully this release will help motivate upstream projects to fix these issues and properly support all ARM64 page sizes (64K, 16K, and 4K). 16K provides a significant performance improvement of up to 20% or so under some workloads, so it’s worth it.

There is a category of software that will likely never support 16K page sizes: certain emulators and compatibility layers, including FEX. Android is also affected, in case someone wants to try running it natively some day. For users of these tools, we will provide 4K page size kernels in the future, once the kernel changes that make this possible are ready for upstreaming.

## Further information

Visit our docs wiki for more information! We could use more people working on documentation, so feel free to contribute too! Note that, since things have been moving very quickly, some of the docs may be out of date.

### Recommended reading:

[“When will Asahi Linux be done?"](https://github.com/AsahiLinux/docs/wiki/%22When-will-Asahi-Linux-be-done%3F%22)
[Introduction to Apple Silicon](https://github.com/AsahiLinux/docs/wiki/Introduction-to-Apple-Silicon)
[Open OS Ecosystem on Apple Silicon Macs](https://github.com/AsahiLinux/docs/wiki/Open-OS-Ecosystem-on-Apple-Silicon-Macs)
[m1n1:User Guide](https://github.com/AsahiLinux/docs/wiki/m1n1%3AUser-Guide)

If you’re a developer or reverse engineer, we have some really cool toys:

[SW:Hypervisor](https://github.com/AsahiLinux/docs/wiki/SW:Hypervisor)

And if you’re bored:

[Trivia](https://github.com/AsahiLinux/docs/wiki/Trivia)

## License

Copyright The Asahi Linux Contributors

The Asahi Linux installer is distributed under the MIT license. See LICENSE for the license text.

This installer vendors [python-asn1](https://github.com/andrivet/python-asn1), which is distributed under the same license.

## Building

`./build.sh`

(README contributed to by @MDNich)

