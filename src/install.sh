#!/bin/sh
# SPDX-License-Identifier: MIT

set -e

if [ "${0%/*}" != "$0" ]; then
  cd "${0%/*}"
fi

export LC_ALL=en_US.UTF-8
export LANG=en_US.UTF-8

export DYLD_LIBRARY_PATH=$PWD/Frameworks/Python.framework/Versions/Current/lib
export DYLD_FRAMEWORK_PATH=$PWD/Frameworks
python=Frameworks/Python.framework/Versions/3.9/bin/python3.9
export SSL_CERT_FILE=$PWD/Frameworks/Python.framework/Versions/Current/etc/openssl/cert.pem
# Bootstrap does part of this, but install.sh can be run standalone
# so do it again for good measure.
export PATH="$PWD/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

set +e
macos_ver=$(/usr/libexec/PlistBuddy -c "Print :ProductVersion" \
  /System/Library/CoreServices/SystemVersion.plist)
res=$?
set -e

if [ "$res" -ne 0 ] || [ -z "$macos_ver" ]; then
  echo "Unable to determine macOS version. Please report a bug."
  exit 1
fi

if [ "${macos_ver%%.*}" -lt 12 ]; then
  echo "This installer requires macOS 12.3 or later."
  exit 1
fi

if ! arch -arm64 ls > /dev/null 2> /dev/null; then
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

  # This loses env vars in some security states, so just re-launch ourselves
  exec arch -arm64 ./install.sh
fi

exec < /dev/tty > /dev/tty 2> /dev/tty
exec $python main.py "$@"
