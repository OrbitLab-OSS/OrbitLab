#!/bin/bash

set -eou pipefail
set -o xtrace

rm -f *.deb
BUILD_DIR="$CHROOT/resources"
rm -f "$BUILD_DIR/BUILD"
ORBITLAB_DIR="$BUILD_DIR/opt/orbitlab"

mkdir -p "$ORBITLAB_DIR"
mv "$CHROOT/rxconfig.py" "$ORBITLAB_DIR"

mv "$CHROOT/orbitlab-backend.pex" "$ORBITLAB_DIR/orbitlab-backend"
mv "$CHROOT/orbital-receiver.pex" "$ORBITLAB_DIR/orbital-receiver"
mv "$CHROOT/scripts/orbitlab-frontend.pex" "$ORBITLAB_DIR/orbitlab-frontend"

mv "$CHROOT/frontend.zip" "$ORBITLAB_DIR"

mv "$BUILD_DIR/orbitlab-backend.service" "$ORBITLAB_DIR"
mv "$BUILD_DIR/orbitlab-frontend.service" "$ORBITLAB_DIR"
mv "$BUILD_DIR/orbital-receiver.service" "$ORBITLAB_DIR"

dpkg-deb --root-owner-group --build "$BUILD_DIR"

VERSION="$(grep "Version" "$BUILD_DIR/DEBIAN/control" | awk '{print $2}')"
mv "$CHROOT/resources.deb" "orbitlab-$VERSION.deb"
