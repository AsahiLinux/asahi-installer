#!/bin/sh
# SPDX-License-Identifier: MIT

set -e

VGID="##VGID##"

self="$0"
cd "${self%%step2.sh}"

system_dir="$(cd ../../../; pwd)"
os_name="${system_dir##*/}"

# clear
printf '\033[2J\033[H'

echo "Asahi Linux installer (second step)"
echo
echo "VGID: $VGID"
echo "System volume: $system_dir"
echo

if ! bputil -d -v "$VGID" | grep -q 'one true recoveryOS'; then
    echo "Your system did not boot in One True RecoveryOS (1TR) mode."
    echo
    echo "To finish the installation, the system must be in this special"
    echo "mode. Perhaps you forgot to hold down the power button, or"
    echo "momentarily released it at some point?"
    echo
    echo "Note that tapping and then pressing the power button again will"
    echo "allow you to see the boot picker screen, but you will not be"
    echo "in the correct 1TR mode. You must hold down the power button"
    echo "in one continuous motion as you power on the machine."
    echo
    echo "Your system will now shut down. Once the screen goes blank,"
    echo "please wait 10 seconds, then press the power button and do not"
    echo "release it until you see the 'Entering startup options...'"
    echo "message, then select '$os_name' again."
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

while ! bputil -nc -v "$VGID"; do
    echo
    echo "bputil failed. Did you mistype your password?"
    echo "Press enter to try again."
    read
done

echo
echo

while ! kmutil configure-boot -c boot.bin --raw --entry-point 2048 --lowest-virtual-address 0 -v "$system_dir"; do
    echo
    echo "kmutil failed. Did you mistype your password?"
    echo "Press enter to try again."
    read
done

echo
echo "Wrapping up..."
echo

mount -u -w "$system_dir"

if [ -e "$system_dir/.IAPhysicalMedia" ]; then
    mv "$system_dir/.IAPhysicalMedia" "$system_dir/IAPhysicalMedia-disabled.plist"
fi

if [ -e "$system_dir/System/Library/CoreServices/SystemVersion-disabled.plist" ]; then
    mv -f "$system_dir/System/Library/CoreServices/SystemVersion"{-disabled,}".plist"
fi

echo
echo "Installation complete! Press enter to reboot."
read

reboot
