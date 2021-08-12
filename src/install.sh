#!/bin/sh
# SPDX-License-Identifier: MIT

set -e

export LC_ALL=C
export LANG=C

if [ -z "$IPSW" ]; then
    #IPSW=https://updates.cdn-apple.com/2021SummerSeed/fullrestores/071-63742/90636AD6-5E0A-4474-B652-A6A5AF4995E2/UniversalMac_12.0_21A5284e_Restore.ipsw
    export IPSW=http://raider.lan:5000/UniversalMac_12.0_21A5284e_Restore.ipsw
fi

export DYLD_FALLBACK_LIBRARY_PATH=$PWD/Frameworks/Python.framework/Versions/Current/lib
export DYLD_FALLBACK_FRAMEWORK_PATH=$PWD/Frameworks
python=Frameworks/Python.framework/Versions/3.9/bin/python3.9
export SSL_CERT_FILE=$PWD/Frameworks/Python.framework/Versions/Current/etc/openssl/cert.pem
export PATH="$PWD/bin:$PATH"

exec </dev/tty >/dev/tty 2>/dev/tty
exec $python main.py "$@"
