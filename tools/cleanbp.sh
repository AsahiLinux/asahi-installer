#!/bin/sh
set -e

cat > /tmp/uuids.txt <<EOF
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
