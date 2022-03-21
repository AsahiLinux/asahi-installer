#!/bin/sh
# SPDX-License-Identifier: MIT

set -e

export LC_ALL=C
export LANG=C

export DYLD_LIBRARY_PATH=$PWD/Frameworks/Python.framework/Versions/Current/lib
export DYLD_FRAMEWORK_PATH=$PWD/Frameworks
python=Frameworks/Python.framework/Versions/3.9/bin/python3.9
export SSL_CERT_FILE=$PWD/Frameworks/Python.framework/Versions/Current/etc/openssl/cert.pem
export PATH="$PWD/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

arch=

if ! arch -arm64 ls >/dev/null 2>/dev/null; then
    echo
    echo "Looks like this is an Intel Mac!"
    echo "Sorry, Asahi Linux only supports Apple Silicon machines."
    echo "May we interest you in https://t2linux.org/ instead?"
    exit 1
fi

if [ $(arch) != "arm64" ]; then
    echo
    echo "You're running the installer in Intel mode under Rosetta!"
    echo "Don't worry, we can fix that for you. Switching to ARM64 mode..."
    arch="arch -arm64"
fi

exec </dev/tty >/dev/tty 2>/dev/tty
exec $arch $python main.py "$@"
