# Asahi Linux installer

The Asahi Linux Installer is designed to facilitate the installation of Asahi Linux on compatible devices. This documentation provides instructions for building, configuring, and deploying the installer, along with licensing information.

## License

Copyright The Asahi Linux Contributors

The Asahi Linux installer is distributed under the MIT license. See LICENSE for the license text.

This installer vendors [python-asn1](https://github.com/andrivet/python-asn1), which is distributed under the same license.

## Building

To build the Asahi Linux installer, run the following command:

```sh
./build.sh
```

By default this will build m1n1 with chainloading support. You can optionally set the following environment variables to customize the build:

- `M1N1_STAGE1`: Path to a prebuilt m1n1 stage 1 binary.
- `LOGO`: Path to a logo in ICNS format.

These options are mainly useful for downstream distributions that want to customize or brand the installer.

**Note*** *Before building the Asahi Linux installer, ensure that all submodules are initialized and updated. Run the following commands:*

```sh
git submodule update --init --recursive
```

### Build Script Overview

The `build.sh` script performs several key steps to build the installer:

- Set Environment Variables
- Download Dependencies
- Copies Files & Certificates
- Build m1n1
- Creates a targall of the package and saves it to the releases directory.

## Deployment

To deploy the built installer, use the upload.sh script:

```sh
./upload.sh [prod|dev]
```

prod: Deploys to the production directory.
dev: Deploys to the development directory.


## Testing the Installer

To test the installer, use the following script:

```sh
test.sh
```

## Additional Information

For more details and updates, visit the [Asahi Linux Installer repository](https://github.com/AsahiLinux/asahi-installer).


