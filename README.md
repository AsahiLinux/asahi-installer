# Asahi Linux installer

TODO: document

## License

Copyright The Asahi Linux Contributors

The Asahi Linux installer is distributed under the MIT license. See LICENSE for the license text.

This installer vendors [python-asn1](https://github.com/andrivet/python-asn1), which is distributed under the same license.

## Building on macOS
### Build Requirements
Install and setup `Xcode Command Line Tools` from Apple
```bash
xcode-select --install
```
Install and setup [`Homebrew`](https://brew.sh/), "The Missing Package Manager for macOS"
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```
Install [Rust and Cargo](https://doc.rust-lang.org/cargo/getting-started/installation.html):
```bash
# follow the installer instructions
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
# afterwards initialize
source "$HOME/.cargo/env"
```

### Build Asahi Installer locally
```bash
git clone --recursive https://github.com/AsahiLinux/asahi-installer.git
cd ./asahi-installer
./build.sh
```

### FAQ Errors
```bash
# Error: Rust dependency not found
error: failed to load source for dependency `bitflags`
# Solution: download rust cargo dependencies for m1n1
cd m1n1
git submodule init
git submodule update
```
