#!/bin/sh
# SPDX-License-Identifier: MIT

set -e

export LC_ALL=C
export LANG=C

export DYLD_LIBRARY_PATH=$PWD/Frameworks/Python.framework/Versions/Current/lib
export DYLD_FRAMEWORK_PATH=$PWD/Frameworks
python=Frameworks/Python.framework/Versions/3.9/bin/python3.9
export SSL_CERT_FILE=$PWD/Frameworks/Python.framework/Versions/Current/etc/openssl/cert.pem
export PATH="$PWD/bin:$PATH"

exec </dev/tty >/dev/tty 2>/dev/tty
exec $python main.py "$@"
