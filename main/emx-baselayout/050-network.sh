#!/bin/sh
# Static network setup. The values come from /etc/emx/network.conf (IFACE, ADDRESS, NETMASK, GATEWAY),
# written by emx-mkimage --ip ... Without the file nothing is configured.

if [ -f /etc/emx/network.conf ]; then
    . /etc/emx/network.conf

    run "Setting up $IFACE" /usr/bin/ifconfig --interface="$IFACE" --address="$ADDRESS" --netmask="${NETMASK:-255.255.255.0}" --up --verbose

    if [ -n "$GATEWAY" ]; then
        run "Setting up gateway" /usr/bin/route "$IFACE" "$GATEWAY"
    fi
fi
