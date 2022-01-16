#!/bin/sh
# SPDX-License-Identifier: MIT

set -e

VGID="##VGID##"

self="$0"
cd "${self%%step2.sh}"

system_dir="$(pwd)"

echo "Asahi Linux installer (step 2)"
echo
echo "VGID: $VGID"
echo "System volume: $system_dir"
echo
echo "You will be prompted for login credentials two times."
echo "Please enter your macOS credentials (for the macOS that you"
echo "used to run the first step of the installation)."
echo
echo "Press enter to continue."
echo

read

bputil -nc -v "$VGID"

if [ -f m1n1.macho ]; then
    kmutil configure-boot -c m1n1.macho -v "$system_dir"
else
    kmutil configure-boot -c m1n1.bin --raw --entry-point 2048 --lowest-virtual-address 0 -v "$system_dir"
fi

echo
echo "Installation complete! Press enter to reboot."
read

reboot
