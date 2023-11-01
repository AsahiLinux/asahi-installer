#!/bin/sh
# SPDX-License-Identifier: MIT

set -e

# Define directory variables
SCRIPT_DIR="$(dirname "$0")"
M1N1="$SCRIPT_DIR/m1n1"
ARTWORK="$SCRIPT_DIR/artwork"
AFW="$SCRIPT_DIR/asahi_firmware"
SRC="$SCRIPT_DIR/src"
VENDOR="$SCRIPT_DIR/vendor"
DL="$SCRIPT_DIR/dl"
PACKAGE="$SCRIPT_DIR/package"
RELEASES="$SCRIPT_DIR/releases"
RELEASES_DEV="$SCRIPT_DIR/releases-dev"

# Create necessary directories
rm -rf "$PACKAGE"
mkdir -p "$DL" "$PACKAGE" "$RELEASES" "$RELEASES_DEV" "$PACKAGE/bin"

# Determine version
VER=$(git describe --always --dirty --tags)
echo "Version: $VER"

if [ -z "$VER" ]; then
    if [ -e "$SCRIPT_DIR/version.tag" ]; then
        VER="$(cat "$SCRIPT_DIR/version.tag")"
    else
        echo "Could not determine version!"
        exit 1
    fi
fi

echo "Downloading installer components..."

cd "$DL"

PYTHON_VER=3.9.6
PYTHON_PKG="python-$PYTHON_VER-macos11.pkg"
PYTHON_URI="https://www.python.org/ftp/python/$PYTHON_VER/$PYTHON_PKG"

wget -Nc "$PYTHON_URI"

echo "Building m1n1..."
make -C "$M1N1" RELEASE=1 CHAINLOADING=1 -j4

echo "Copying files..."
cp -r "$SRC"/* "$PACKAGE/"
rm "$PACKAGE/asahi_firmware"
cp -r "$AFW" "$PACKAGE/"
cp "$ARTWORK/logos/icns/AsahiLinux_logomark.icns" "$PACKAGE/logo.icns"
mkdir -p "$PACKAGE/boot"
cp "$M1N1/build/m1n1.bin" "$PACKAGE/boot"

echo "Extracting Python framework..."
mkdir -p "$PACKAGE/Frameworks/Python.framework"

7z x -so "$DL/$PYTHON_PKG" Python_Framework.pkg/Payload | zcat | cpio -i -D "$PACKAGE/Frameworks/Python.framework"

cd "$PACKAGE/Frameworks/Python.framework/Versions/Current"

echo "Copying vendored libffi into Python framework..."
cp -P "$VENDOR/libffi"/* lib/

echo "Slimming down Python..."
rm -rf include share
cd lib
rm -rf -- tdb* tk* Tk* libtk* *tcl*
cd python3.*
rm -rf test ensurepip idlelib
cd lib-dynload
rm -f _test* _tkinter*

echo "Copying certificates..."
certs="$(python3 -c 'import certifi; print(certifi.where()')"
cp "$certs" "$PACKAGE/Frameworks/Python.framework/Versions/Current/etc/openssl/cert.pem"

echo "Packaging installer..."
cd "$PACKAGE"

echo "$VER" > version.tag

if [ "$1" == "prod" ]; then
    PKGFILE="$RELEASES/installer-$VER.tar.gz"
    LATEST="$RELEASES/latest"
elif [ "$1" == "dev" ]; then
    PKGFILE="$RELEASES_DEV/installer-$VER.tar.gz"
    LATEST="$RELEASES_DEV/latest"
else
    PKGFILE="../installer.tar.gz"
    LATEST="../latest"
fi

tar czf "$PKGFILE" .

echo "Built package: $(basename "$PKGFILE")"
