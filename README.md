# Asahi Linux installer
The Asahi Linux installer provides a way to install [Asahi Linux](https://asahilinux.org)
on Apple Silicon Macs. These systems have a bespoke [boot process](https://asahilinux.org/docs/platform/introduction/)
that requires special considerations to support [alternative operating systems](https://asahilinux.org/docs/platform/open-os-interop/).
The Asahi Installer takes care of preparing the system for the installation,
downloading an image of the distribution to install and laying it on disk.

This repository provides the installer itself, supporting scripts, and the
`asahi_firmware` Python module (which is also used by [asahi-scripts](https://github.com/AsahiLinux/asahi-scripts)).

## Building
Run `./build.sh`, which will produce an installer tree under `releases/`. By
default this will build m1n1 with chainloading support. You can optionally set
`M1N1_STAGE1` to a prebuilt m1n1 stage 1 binary, and `LOGO` to a logo in icns format.
These are mostly useful for downstream distributions that would like to customize
or brand the installer. By default, the build will fetch required dependencies from
the Internet and cache them under `dl/`. If this isn't desired, place the required
files there before running the build.

The reference installer at https://alx.sh is deployed from the latest tag of this
repo by `.github/workflows/release-prod.yaml`. The dev installer at https://alx.sh/dev
is deployed from the latest push to `main` by `.github/workflows/release-dev.yaml`.

## Bootstrapping and branding
The installer is meant to be executed via a bootstrap script. We provide reference
implementations for [local development](scripts/bootstrap.sh) and for alx.sh
([prod](scripts/bootstrap-prod.sh), [dev](scripts/bootstrap-dev.sh)). Following
our [distribution guidelines](https://asahilinux.org/docs/alt/policy/), downstream
distributions are encouraged to host their own modified copy of these, alongside
their downstream build of the installer and their installation images. Downstreams
will also want to customize the variable definitions at the beginning of the script,
as those will be consumed by the installer and used for its branding. These include:

* `VERSION_FLAG`: a URI pointing to the `latest` file within the installer tree
* `INSTALLER_BASE`: a URL pointing to your installer tree
* `INSTALLER_DATA`: a URI pointing to your installer medatata file (see
  [asahi-installer-data](https://github.com/AsahiLinux/asahi-installer) for
  the one we're using for alx.sh)
* `INSTALLER_DATA_ALT`: optionally, a URI pointing to an alternative location for
  your installer metadata file; this can be useful in locations where the
  primary location might be blocked by local network policies
* `REPO_BASE`: a URI pointing to your OS images root (meaning, the parent folder
  of the relative paths referenced inside the metadata file)
* `REPORT`: a URI pointing to the stats server for installation metrics collection
* `REPORT_TAG`: a string used to identify your distribution for metrics collection

## License
Copyright The Asahi Linux Contributors

The Asahi Linux installer is distributed under the MIT license. See LICENSE for the
license text.

This installer vendors [python-asn1](https://github.com/andrivet/python-asn1), which
is distributed under the same license.
