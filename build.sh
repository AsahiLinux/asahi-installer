#!/bin/sh
# SPDX-License-Identifier: MIT

set -e

cd "$(dirname "$0")"

PYTHON_VER=3.9.6
PYTHON_PKG=python-$PYTHON_VER-macos11.pkg
PYTHON_URI="https://www.python.org/ftp/python/$PYTHON_VER/$PYTHON_PKG"

LIBFFI_VER=3.4.6
LIBFFI_MANIFEST_URI="https://ghcr.io/v2/homebrew/core/libffi/manifests/$LIBFFI_VER"
LIBFFI_BASE_URI="https://ghcr.io/v2/homebrew/core/libffi/blobs"
LIBFFI_TARGET_OS="macOS 12.6"
LIBFFI_PKG="libffi-$LIBFFI_VER-macos.tar.gz"

M1N1="$PWD/m1n1"
ARTWORK="$PWD/artwork"
AFW="$PWD/asahi_firmware"
SRC="$PWD/src"
DL="$PWD/dl"
PACKAGE="$PWD/package"
RELEASES="$PWD/releases"
RELEASES_DEV="$PWD/releases-dev"

rm -rf "$PACKAGE"

mkdir -p "$DL" "$PACKAGE" "$RELEASES" "$RELEASES_DEV"
mkdir -p "$PACKAGE/bin"

echo "Determining version..."

[ -d .git ] && VER=$(git describe --always --dirty --tags)

if [ -z "$VER" ]; then
    if [ -e version.tag ]; then
        VER="$(cat version.tag)"
    else
        echo "Could not determine version!"
        exit 1
    fi
fi

echo "Version: $VER"

echo "Downloading installer components..."

cd "$DL"

echo " - Python"

if [ -e "$PYTHON_PKG" ]; then
    echo "Using existing $PYTHON_PKG"
else
    wget -Nc "$PYTHON_URI"
fi

echo " - libffi"

if [ -e "$LIBFFI_PKG" ]; then
    echo "Using existing $LIBFFI_PKG"
else
    # get a JSON with an anonymous token
    token=$(curl -s "https://ghcr.io/token?service=ghcr.io&scope=repository%3Ahomebrew/core/go%3Apull" | jq -jr ".token")

    digest=$( \
        curl -s \
        -H "Authorization: Bearer ${token}" \
        -H 'Accept: application/vnd.oci.image.index.v1+json' \
        $LIBFFI_MANIFEST_URI \
        | jq -r '[.manifests[] |
                select(.platform.architecture == "arm64"
                and .platform."os.version" == "'"$LIBFFI_TARGET_OS"'")
            ] | first | .annotations."sh.brew.bottle.digest"' \
    )

    curl -L -o "$LIBFFI_PKG" \
        -H "Authorization: Bearer ${token}" \
        -H 'Accept: application/vnd.oci.image.index.v1+json' \
        "$LIBFFI_BASE_URI/sha256:$digest"
fi

if [ -r "$M1N1_STAGE1" ]; then
    echo "Using '$M1N1_STAGE1' as m1n1 stage1"
elif [ ! -r "$M1N1/Makefile" ]; then
    echo "m1n1 missing, did you forget to update the submodules?"
    exit 1
else
    echo "Building m1n1..."

    # Do it twice in case of build system shenanigans with versions
    make -C "$M1N1" RELEASE=1 CHAINLOADING=1 -j4
    make -C "$M1N1" RELEASE=1 CHAINLOADING=1 -j4

    M1N1_STAGE1="$M1N1/build/m1n1.bin"
fi

echo "Copying files..."

cp -r "$SRC"/* "$PACKAGE/"
rm -rf "$PACKAGE/asahi_firmware"
cp -r "$AFW" "$PACKAGE/"
if [ -r "$LOGO" ]; then
    cp "$LOGO" "$PACKAGE/logo.icns"
elif [ ! -r "$ARTWORK/logos/icns/AsahiLinux_logomark.icns" ]; then
    echo "artwork missing, did you forget to update the submodules?"
    exit 1
else
    cp "$ARTWORK/logos/icns/AsahiLinux_logomark.icns" "$PACKAGE/logo.icns"
fi
mkdir -p "$PACKAGE/boot"
cp "$M1N1_STAGE1" "$PACKAGE/boot/m1n1.bin"

echo "Extracting libffi..."

cd "$PACKAGE"
tar xf "$DL/$LIBFFI_PKG"

echo "Extracting Python framework..."

mkdir -p "$PACKAGE/Frameworks/Python.framework"

7z x -so "$DL/$PYTHON_PKG" Python_Framework.pkg/Payload | zcat | \
    (cd "$PACKAGE/Frameworks/Python.framework"; cpio -i)


cd "$PACKAGE/Frameworks/Python.framework/Versions/Current"

echo "Moving in libffi..."

mv "$PACKAGE/libffi/$LIBFFI_VER/lib/"libffi*.dylib lib/
rm -rf "$PACKAGE/libffi"

echo "Slimming down Python..."

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

echo "$VER" > version.tag

PKGFILE="$RELEASES/installer-$VER.tar.gz"
LATEST="$RELEASES/latest"

tar czf "$PKGFILE" .
echo "$VER" > "$LATEST"

echo
echo "Built package: $(basename "$PKGFILE")"
