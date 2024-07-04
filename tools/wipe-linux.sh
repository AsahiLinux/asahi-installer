#!/bin/sh
set -e

echo "THIS SCRIPT IS DANGEROUS!"
echo "DO NOT BLINDLY RUN IT IF SOMEONE JUST SENT YOU HERE."
echo "IT WILL INDISCRIMINATELY WIPE A BUNCH OF PARTITIONS"
echo "THAT MAY OR MAY NOT BE THE ONES YOU WANT TO WIPE."
echo
echo "You are much better off reading and understanding this guide:"
echo "https://github.com/AsahiLinux/docs/wiki/Partitioning-cheatsheet"
echo
echo "Press enter twice if you really want to continue."
echo "Press Control-C to exit."

read
read

diskutil list | grep Apple_APFS | grep '\b2\.5 GB' | sed 's/.* //g' | while read i; do
  diskutil apfs deleteContainer "$i"
done
diskutil list /dev/disk0 | grep -Ei 'asahi|linux|EFI' | sed 's/.* //g' | while read i; do
  diskutil eraseVolume free free "$i"
done

cat > /tmp/uuids.txt << EOF
3D3287DE-280D-4619-AAAB-D97469CA9C71
C8858560-55AC-400F-BBB9-C9220A8DAC0D
EOF

diskutil apfs listVolumeGroups >> /tmp/uuids.txt

cd /System/Volumes/iSCPreboot

for i in ????????-????-????-????-????????????; do
  if grep -q "$i" /tmp/uuids.txt; then
    echo "KEEP $i"
  else
    echo "RM $i"
    rm -rf "$i"
  fi
done
