#!/bin/sh
set -e

cd "$(dirname "$0")"

SECRET_FILE=~/.secrets/asahilinux-storage
BASEPATH=https://storage.bunnycdn.com/asahilinux
SRC=releases

case "$1" in
  prod) DIR=installer ;;
  dev) DIR=installer-dev ;;
  *)
     echo "Usage: $0 [prod|dev]" 1>&2
     exit 1
     ;;
esac

if [ ! -e "$SECRET_FILE" ]; then
  echo "Missing storage bucket secret. Please place the secret in $SECRET_FILE." 1>&2
  exit 1
fi

SECRET="$(cat "$SECRET_FILE")"

put() {
  curl -# --fail --request PUT \
    --url "$1" \
    --header "AccessKey: $SECRET" \
    --header "Content-Type: $2" \
    --header 'accept: application/json' \
    --data-binary @$3 > /tmp/ret
  ret=$?
  cat /tmp/ret
  echo
  echo
  return $ret
}

VERSION="$(cat $SRC/latest)"
FILE="installer-${VERSION}.tar.gz"
SRCFILE="$SRC/$FILE"
TARGETFILE="$BASEPATH/$DIR/$FILE"

if [ ! -e "$SRCFILE" ]; then
  echo "$SRCFILE does not exist" 1>&2
  exit 1
fi

echo "About to push version $VERSION from $SRCFILE to $TARGETFILE."
echo "Press enter to confirm."

read

put "$TARGETFILE" "application/octet-stream" "$SRCFILE"

echo "Updating latest flag..."

put "$BASEPATH/$DIR/latest" "text/plain" "$SRC/latest"

echo "Done!"
