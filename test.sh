#!/bin/sh
set -e

cd "$(dirname "$0")"
base="$PWD"

if [ -e $HOME/.cargo/env ]; then
  source $HOME/.cargo/env
fi

export INSTALLER_BASE=https://cdn.asahilinux.org/installer-dev
export REPO_BASE=https://cdn.asahilinux.org

make -C "m1n1" RELEASE=1 CHAINLOADING=1 -j4

sudo rm -rf /tmp/asahi-install
mkdir -p /tmp/asahi-install

git describe --tags --always --dirty > /tmp/asahi-install/version.tag

cd /tmp/asahi-install
ln -sf "$base/src"/* .
ln -sf "$base/asahi_firmware" .
mkdir -p boot
ln -sf "$base/m1n1/build/m1n1.bin" boot/m1n1.bin
ln -sf "$base/artwork/logos/icns/AsahiLinux_logomark.icns" logo.icns
ln -sf "$base/data/installer_data.json" installer_data.json

sudo -E python3 main.py
