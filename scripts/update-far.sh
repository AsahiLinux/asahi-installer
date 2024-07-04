#!/bin/bash
set -e

cd "$(dirname "$0")/.."

VERSION="Fedora Linux 40"
TARGET_VERSION="Fedora Asahi Remix 40"
PACKAGE_BASE="https://asahilinux-fedora.b-cdn.net/os/"

curl -s https://fedora-asahi-remix.org/installer_data.json > /tmp/far.json

BUILD=$(jq -r \
  ".os_list[].name | select(. | test(\"$VERSION\")) | sub(\".*\\\\((?<i>.*)\\\\).*\"; \"\\(.i)\")" < /tmp/far.json |
    sort -r | head -1)

echo "Using build: $BUILD"

jq < data/installer_data.json > /tmp/new.json --indent 4 --slurpfile far /tmp/far.json \
  ".os_list |=
    [
      \$far[0].os_list[]
      | select(.name | test(\"$VERSION.*$BUILD\"))
      | (.name |= sub(\"$VERSION (?<i>.*) \\\\(.*\\\\)\"; \"$TARGET_VERSION \\(.i)\"))
      | (.package |= \"$PACKAGE_BASE\" + .)
    ] +
    [
      .[] | select(.name | test(\"Fedora\") == false)
    ]
  "

diff -u data/installer_data.json /tmp/new.json && echo "No change" && exit 0

if [ "$1" == "-u" ]; then
  git diff-index --quiet --cached HEAD -- || {
      echo "There are uncommitted changes, not updating"
      exit 1
  }
  mv /tmp/new.json data/installer_data.json
  git add data/installer_data.json
  git commit -s -m "installer_data: Update to $TARGET_VERSION $BUILD"
fi
