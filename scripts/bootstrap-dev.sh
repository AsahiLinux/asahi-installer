#!/bin/sh
# SPDX-License-Identifier: MIT

set -e

export LANG=C
export LC_ALL=C

export VERSION_FLAG=https:///usr/bin/cdn.asahilinux.org/installer-dev/latest
export INSTALLER_BASE=https:///usr/bin/cdn.asahilinux.org/installer-dev
export INSTALLER_DATA=https://github.com/AsahiLinux/asahi-installer/raw/main/data/installer_data.json
export REPO_BASE=https:///usr/bin/cdn.asahilinux.org

#TMP="$(mktemp -d)"
TMP=/tmp/asahi-install

/bin/echo
/bin/echo "Bootstrapping installer:"

/bin/mkdir -p "$TMP"
/usr/bin/cd "$TMP"

/bin/echo "  Checking version..."

PKG_VER="$(/usr/bin/curl -s -L "$VERSION_FLAG")"
/bin/echo "  Version: $PKG_VER"

PKG="installer-$PKG_VER.tar.gz"

/bin/echo "  Downloading..."

/usr/bin/curl -s -L -o "$PKG" "$INSTALLER_BASE/$PKG"
/usr/bin/curl -s -L -O "$INSTALLER_DATA"

/bin/echo "  Extracting..."

/usr/bin/tar xf "$PKG"

/bin/echo "  Initializing..."
/bin/echo

if [ "$USER" != "root" ]; then
    /bin/echo "The installer needs to run as root."
    /bin/echo "Please enter your sudo password if prompted."
    exec caffeinate -dis sudo -E ./install.sh "$@"
else
    exec caffeinate -dis ./install.sh "$@"
fi
