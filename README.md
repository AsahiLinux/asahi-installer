# Asahi Linux installer

This is the repository for the Asahi Linux installer. It is a Python script that is designed to run on MacOS running on
Apple Silicon Macs (M1/M2), and installs Asahi Linux by allowing the user to choose partitions, then downloading and
installing Asahi Linux.

This is the script that is found at `curl https://alx.sh | sh`.

## Contributing

Please read the [CONTRIBUTING.md] documentation. This outlines how to setup a basic development environment and contributing back changes.

## Building

1. `git clone https://github.com/AsahiLinux/asahi-installer --recursive`
2. `cd asahi-installer`
3. `./build.sh`

## License

Copyright The Asahi Linux Contributors

The Asahi Linux installer is distributed under the MIT license. See LICENSE for the license text.

This installer vendors [python-asn1](https://github.com/andrivet/python-asn1), which is distributed under the same license.