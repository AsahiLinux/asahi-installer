#!/bin/sh
set -e

/bin/cat > /tmp/uuids.txt <<EOF
3D3287DE-280D-4619-AAAB-D97469CA9C71
C8858560-55AC-400F-BBB9-C9220A8DAC0D
EOF

/usr/sbin/diskutil apfs listVolumeGroups >> /tmp/uuids.txt

/usr/bin/cd /System/Volumes/iSCPreboot

for i in ????????-????-????-????-????????????; do
    if /usr/bin/grep -q "$i" /tmp/uuids.txt; then
        /bin/echo "KEEP $i"
    else
        /bin/echo "RM $i"
        /bin/rm -rf "$i"
    fi
done
