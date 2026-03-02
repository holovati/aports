#!/bin/bash

set -e

if [ -z "$SYSROOT" ] || [ -z "$EMXREPO" ]; then
    echo "SYSROOT and EMXREPO must be set";
    exit 1
fi
    
mkdir -p "$SYSROOT"/etc/apk

echo "$EMXREPO" > "$SYSROOT"/etc/apk/repositories

apk --allow-untrusted --root "$SYSROOT" --initdb add emx-base || true

cp -rv "$SYSROOT"/lib/* "$SYSROOT"/usr/lib/
rm -rf "$SYSROOT"/lib

ln -sf /usr/bin "$SYSROOT"/bin
ln -sf /usr/sbin "$SYSROOT"/sbin
ln -sf /usr/lib "$SYSROOT"/lib

sysroot_name=`basename "$SYSROOT"`

tar czfv "$sysroot_name".tar.gz "$SYSROOT"
