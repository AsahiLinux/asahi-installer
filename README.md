# Asahi Linux installer 

Linux installation for Apple Silicon Macs.

## About

Asahi Linux is a Linux distribution that's designed for Apple Silicon Macbooks. Because of Apple's owned and licensed hardware and software, there are more complications and issues with compatibility and speed when running Linux. This installer makes installation of Asahi a lot easier automating and securing much of its processes.

Some important features include:
- Partitioning
- Bootloader configuration
- Boot Compatibility/Dual Booting
- Upstream Kernel Integration

In the future we hope to enhance compatibility between Linux and hardware and increase performance.

## Installation

**Prerequisites:**
- Macbook with M1, M2, or M3 chip
- 50GB of available disk space

**Step 1:** Run the following command in the terminal to download and start the installer:
```
curl https://alx.sh | sh
```

**Step 2:** Select default or advanced installation type and select Minimal, Desktop, or custom variant.

**Step 3:** Restart laptop and boot Asahi Linux.

**Step 4:** Update in the terminal with this command:
```
sudo pacman -Syu
```

## Contributing

To contribute, set up the development environment by running these commands in the terminal:
```
sudo pacman -S base-devel python git
```
Then:
```
pip install -r requirements.txt
```

Thank you to all our current and past contributors!
<a href="https://github.com/AsahiLinux/asahi-installer/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=AsahiLinux/asahi-installer" />
</a>

## Building

`./build.sh`

By default this will build m1n1 with chainloading support. You can optionally set `M1N1_STAGE1` to a prebuilt m1n1 stage 1 binary, and `LOGO` to a logo in icns format. These are mostly useful for downstream distributions that would like to customize or brand the installer.

## License

Copyright The Asahi Linux Contributors

The Asahi Linux installer is distributed under the MIT license. See LICENSE for the license text.

This installer vendors [python-asn1](https://github.com/andrivet/python-asn1), which is distributed under the same license.

