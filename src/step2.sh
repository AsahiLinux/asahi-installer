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

if ! bputil -d -v "$VGID" | grep -q 'one true recoveryOS'; then
    echo "Your system did not boot in One True RecoveryOS (1TR) mode."
    echo
    echo "To perform step 2 of the installation, the system must be in"
    echo "this special mode. Perhaps you forgot to hold down the power"
    echo "button, or momentarily released it at some point?"
    echo
    echo "Note that tapping and then pressing the power button again will"
    echo "allow you to see the boot picker screen, but you will not be"
    echo "in the correct 1TR mode. You must hold down the power button"
    echo "in one continuous motion as you power on the machine."
    echo
    echo "Your system will now shut down. Once the screen goes blank,"
    echo "please wait 10 seconds, then press the power button and do not"
    echo "release it until you see the 'Entering startup options...'"
    echo "message, then try running this script from recoveryOS again."
    echo
    echo "Press enter to shut down your system."
    read
    shutdown -h now
    exit 1
fi

echo "You will be prompted for login credentials two times."
echo "Please enter your macOS credentials (for the macOS that you"
echo "used to run the first step of the installation)."
echo
echo "Press enter to continue."
echo

read

bputil -nc -v "$VGID"

echo
echo

if [ -f m1n1.macho ]; then
    kmutil configure-boot -c m1n1.macho -v "$system_dir"
else
    kmutil configure-boot -c m1n1.bin --raw --entry-point 2048 --lowest-virtual-address 0 -v "$system_dir"
fi

echo
echo "Installation complete! Press enter to reboot."
read

reboot
