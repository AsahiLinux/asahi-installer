#!/bin/sh
# SPDX-License-Identifier: MIT

set -e

/usr/bin/cd "$(dirname "$0")"

PYTHON_VER=3.9.6
PYTHON_PKG=python-$PYTHON_VER-macos11.pkg
PYTHON_URI="https://www.python.org/ftp/python/$PYTHON_VER/$PYTHON_PKG"

M1N1="$PWD/m1n1"
ARTWORK="$PWD/artwork"
SRC="$PWD/src"
DL="$PWD/dl"
PACKAGE="$PWD/package"
RELEASES="$PWD/releases"
RELEASES_DEV="$PWD/releases-dev"

/bin/rm -rf "$PACKAGE"

/bin/mkdir -p "$DL" "$PACKAGE" "$RELEASES" "$RELEASES_DEV"
/bin/mkdir -p "$PACKAGE/bin"

/bin/echo "Determining version..."

VER=$(/usr/bin/git describe --always --dirty --tags)

/bin/echo "Version: $VER"

if [ -z "$VER" ]; then
    if [ -e version.tag ]; then
        VER="$(/bin/cat version.tag)"
    else
        /bin/echo "Could not determine version!"
        exit 1
    fi
fi

/bin/echo "Downloading installer components..."

/usr/bin/cd "$DL"

wget -Nc "$PYTHON_URI"

/bin/echo "Building m1n1..."

/usr/bin/make -C "$M1N1" RELEASE=1 CHAINLOADING=1 -j4

/bin/echo "Copying files..."

/bin/cp -r "$SRC"/* "$PACKAGE/"
/bin/cp "$ARTWORK/logos/icns/AsahiLinux_logomark.icns" "$PACKAGE/logo.icns"
/bin/mkdir -p "$PACKAGE/boot"
/bin/cp "$M1N1/build/m1n1.bin" "$PACKAGE/boot"

/bin/echo "Extracting Python framework..."

/bin/mkdir -p "$PACKAGE/Frameworks/Python.framework"

7z x -so "$DL/$PYTHON_PKG" Python_Framework.pkg/Payload | /usr/bin/zcat | \
    /usr/bin/cpio -i -D "$PACKAGE/Frameworks/Python.framework"

/bin/echo "Slimming down Python..."

/usr/bin/cd "$PACKAGE/Frameworks/Python.framework/Versions/Current"

/bin/rm -rf include share
/usr/bin/cd lib
/bin/rm -rf -- tdb* tk* Tk* libtk* *tcl*
/usr/bin/cd python3.*
/bin/rm -rf test ensurepip idlelib
/usr/bin/cd lib-dynload
/bin/rm -f _test* _tkinter*
    
/bin/echo "Copying certificates..."

certs="$(/usr/bin/python3 -c 'import certifi; print(certifi.where())')"
/bin/cp "$certs" "$PACKAGE/Frameworks/Python.framework/Versions/Current/etc/openssl/cert.pem"

/bin/echo "Packaging installer..."

/usr/bin/cd "$PACKAGE"

/bin/echo "$VER" > version.tag

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

/usr/bin/tar czf "$PKGFILE" .
/bin/echo "$VER" > "$LATEST"

/bin/echo
/bin/echo "Built package: $(/usr/bin/basename "$PKGFILE")"
