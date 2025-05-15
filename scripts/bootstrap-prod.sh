#!/bin/sh
# SPDX-License-Identifier: MIT

# Truncation guard
if true; then
    set -e

    if [ ! -e /System ]; then
        echo "You appear to be running this script from Linux or another non-macOS system."
        echo "Asahi Linux can only be installed from macOS (or recoveryOS)."
        exit 1
    fi

    export LC_ALL=en_US.UTF-8
    export LANG=en_US.UTF-8
    export PATH="/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

    if ! curl --no-progress-meter file:/// >/dev/null 2>&1; then
        echo "Your version of cURL is too old. This usually means your macOS is very out"
        echo "of date. Installing Asahi Linux requires at least macOS version 13.5."
        exit 1
    fi

    export VERSION_FLAG=https://cdn.asahilinux.org/installer/latest
    export INSTALLER_BASE=https://cdn.asahilinux.org/installer
    export INSTALLER_DATA=https://github.com/AsahiLinux/asahi-installer-data/raw/prod/data/installer_data.json
    export INSTALLER_DATA_ALT=https://alx.sh/installer_data.json
    export REPO_BASE=https://cdn.asahilinux.org
    export REPORT=https://stats.asahilinux.org/report
    export REPORT_TAG=alx-prod

    #TMP="$(mktemp -d)"
    TMP=/tmp/asahi-install

    echo
    echo "Bootstrapping installer:"

    if [ -e "$TMP" ]; then
        mv "$TMP" "$TMP-$(date +%Y%m%d-%H%M%S)"
    fi

    mkdir -p "$TMP"
    cd "$TMP"

    echo "  Checking version..."

    PKG_VER="$(curl --no-progress-meter -L "$VERSION_FLAG")"
    echo "  Version: $PKG_VER"

    PKG="installer-$PKG_VER.tar.gz"

    echo "  Downloading..."

    curl --no-progress-meter -L -o "$PKG" "$INSTALLER_BASE/$PKG"
    if ! curl --no-progress-meter -L -O "$INSTALLER_DATA"; then
        echo "    Error downloading installer_data.json. GitHub might be blocked in your network."
        echo "    Please consider using a VPN if you experience issues."
        echo "    Trying workaround..."
        curl --no-progress-meter -L -O "$INSTALLER_DATA_ALT"
    fi

    echo "  Extracting..."

    tar xf "$PKG"

    echo "  Initializing..."
    echo

    if [ "$USER" != "root" ]; then
        echo "The installer needs to run as root."
        echo "Please enter your sudo password if prompted."
        exec caffeinate -dis sudo -E ./install.sh "$@"
    else
        exec caffeinate -dis ./install.sh "$@"
    fi
fi
