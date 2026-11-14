#!/bin/sh

run "Clean /tmp dir" /usr/bin/rm -rf /tmp/*

run "Remove FUSE temp files" /usr/bin/find / -name '.fuse*' -exec rm {} \;

run "Syncing" sync
