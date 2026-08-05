#!/bin/sh
# Ensure the cache directory is writable by appuser (UID 10001).
# This runs as root before exec-ing the main command as appuser.
mkdir -p /app/cache
chown -R appuser:appuser /app/cache
exec gosu appuser "$@"
