#!/bin/sh
# SPDX-License-Identifier: MIT

set -e

cd "$(dirname "$0")"

PYTHON_VER=3.9.6
PYTHON_PKG=python-$PYTHON_VER-macos11.pkg
PYTHON_URI="https://www.python.org/ftp/python/$PYTHON_VER/$PYTHON_PKG"

M1N1="$PWD/m1n1"
ARTWORK="$PWD/artwork"
SRC="$PWD/src"
DL="$PWD/dl"
PACKAGE="$PWD/package"

rm -rf "$PACKAGE"

mkdir -p "$DL" "$PACKAGE"
mkdir -p "$PACKAGE/bin"

echo "Downloading installer components..."

cd "$DL"

wget -Nc "$PYTHON_URI"

echo "Building m1n1..."

make -C "$M1N1" RELEASE=1 CHAINLOADING=1 -j4

echo "Copying files..."

cp -r "$SRC"/* "$PACKAGE/"
cp "$ARTWORK/logos/icns/AsahiLinux_logomark.icns" "$PACKAGE/logo.icns"
mkdir -p "$PACKAGE/boot"
cp "$M1N1/build/m1n1.bin" "$PACKAGE/boot"

echo "Extracting Python framework..."

mkdir -p "$PACKAGE/Frameworks/Python.framework"

7z x -so "$DL/$PYTHON_PKG" Python_Framework.pkg/Payload | zcat | \
    cpio -i -D "$PACKAGE/Frameworks/Python.framework"

echo "Slimming down Python..."

cd "$PACKAGE/Frameworks/Python.framework/Versions/Current"

rm -rf include share
cd lib
rm -rf -- tdb* tk* Tk* libtk* *tcl*
cd python3.*
rm -rf test ensurepip idlelib
cd lib-dynload
rm -f _test* _tkinter*
    
echo "Copying certificates..."

certs="$(python3 -c 'import certifi; print(certifi.where())')"
cp "$certs" "$PACKAGE/Frameworks/Python.framework/Versions/Current/etc/openssl/cert.pem"

echo "Packaging installer..."

cd "$PACKAGE"

tar czf ../installer.tar.gz .

