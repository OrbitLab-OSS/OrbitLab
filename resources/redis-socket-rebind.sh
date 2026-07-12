#!/usr/bin/env bash

set -eou pipefail

VMID=$(
    grep -rl "/run/redis,mp=/var/redis" /etc/pve/lxc \
    | sed 's#.*/##' \
    | sed 's#\.conf##' \
    | head -n1
)

[ -z "$VMID" ] && exit 0

echo "Removing stale mp0 from $VMID"
pct set "$VMID" -delete mp0

echo "Stopping $VMID"
pct stop "$VMID"

echo "Re-binding Redis socket to $VMID"
pct set "$VMID" -mp0 '/run/redis,mp=/var/redis'

echo "Starting $VMID"
pct start "$VMID"
