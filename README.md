# Asahi Linux Installer

TODO: document

## License

Copyright The Asahi Linux Contributors

The Asahi Linux installer is distributed under the MIT license. See LICENSE for the license text.

This installer vendors [python-asn1](https://github.com/andrivet/python-asn1), which is distributed under the same license.

## Building

`./build.sh`

By default this will build m1n1 with chainloading support. You can optionally set `M1N1_STAGE1` to a prebuilt m1n1 stage 1 binary, and `LOGO` to a logo in icns format. These are mostly useful for downstream distributions that would like to customize or brand the installer.
