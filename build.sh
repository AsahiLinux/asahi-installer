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

if [[ $OSTYPE == 'darwin'* ]]; then
  export USE_CLANG=1
  echo 'Running on macOS'
    if ! [ -x "$(command -v dtc)" ]; then
    echo 'Error: dtc is not installed. (brew install dtc)' >&2
    exit 1
    fi
    if ! [ -x "$(command -v convert)" ]; then
    echo 'Error: convert is not installed. (brew install imagemagick)' >&2
    exit 1
    fi
    if ! [ -x "$(command -v llvm-objcopy)" ]; then
    echo 'Error: llvm-objcopy is not installed. (brew install llvm)' >&2
    exit 1
    fi
fi

rm -rf "$PACKAGE"

mkdir -p "$DL" "$PACKAGE"
mkdir -p "$PACKAGE/bin"

echo "Updating submodules..."

git submodule update --init --recursive

echo "Downloading installer components..."

cd "$DL"

wget -Nc "$PYTHON_URI"

echo "Building m1n1..."

make -C "$M1N1"

echo "Copying files..."

cp -r "$SRC"/* "$PACKAGE/"
cp "$ARTWORK/logos/icns/AsahiLinux_logomark.icns" "$PACKAGE/logo.icns"
cp "$M1N1/build/m1n1.macho" "$PACKAGE"

echo "Extracting Python framework..."

mkdir -p "$PACKAGE/Frameworks/Python.framework"
cd "$PACKAGE/Frameworks/Python.framework"
7z x -so "$DL/$PYTHON_PKG" Python_Framework.pkg/Payload | zcat | cpio -i

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

pip3 install certifi --user
certs="$(python3 -c 'import certifi; print(certifi.where())')"
cp "$certs" "$PACKAGE/Frameworks/Python.framework/Versions/Current/etc/openssl/cert.pem"

echo "Packaging installer..."

cd "$PACKAGE"

tar czf ../installer.tar.gz .

