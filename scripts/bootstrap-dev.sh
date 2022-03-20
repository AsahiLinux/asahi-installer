#!/bin/sh
# SPDX-License-Identifier: MIT

set -e

export LANG=C
export LC_ALL=C

export VERSION_FLAG=https://cdn.asahilinux.org/installer-dev/latest
export INSTALLER_BASE=https://cdn.asahilinux.org/installer-dev
export INSTALLER_DATA=https://github.com/AsahiLinux/asahi-installer/raw/main/data/installer_data.json
export REPO_BASE=https://cdn.asahilinux.org

#TMP="$(mktemp -d)"
TMP=/tmp/asahi-install

echo
echo "Bootstrapping installer:"

echo "  Checking divice..."
DIVICE_CLASS=`ioreg | grep -iE 'j274ap|j293ap|j313ap|j456ap|j457ap|j314cap|j314sap|j316cap|j316sap'` || true

if [ -z "$DIVICE_CLASS" ]; then
    echo
    echo "  Your mac may not be supported to install."
    echo "  Please check the list of support."
    echo "  exit..."
    exit 1
fi

mkdir -p "$TMP"
cd "$TMP"

echo "  Checking version..."

PKG_VER="$(curl -s -L "$VERSION_FLAG")"
echo "  Version: $PKG_VER"

PKG="installer-$PKG_VER.tar.gz"

echo "  Downloading..."

curl -s -L -o "$PKG" "$INSTALLER_BASE/$PKG"
curl -s -L -O "$INSTALLER_DATA"

echo "  Extracting..."

tar xf "$PKG"

echo "  Initializing..."
echo

if [ "$USER" != "root" ]; then
    echo "The installer needs to run as root."
    echo "Please enter your sudo password if prompted."
    exec sudo -E ./install.sh "$@"
else
    exec ./install.sh "$@"
fi
