#!/usr/bin/env bash

set -euo pipefail

echo "Running all privileged units"

# GDM runs these per-user hooks from greeter and initial-setup sessions
# before any real user logs in. Those sessions run as a transient account:
# the gdm-greeter account, or another gdm-* account under /run/gdm/home
# (GDM 49+ runs initial-setup this way, and its SHELL is not listed in
# /etc/shells), so pkexec logs an error for each one (#688, #691).
# Privileged hooks stamp once-only completion system-wide, so there is
# nothing for them to do here: skip and let the first real login escalate
# and run them.
if [[ "$(id -un)" == gdm-* || "${HOME:-}" == /run/gdm/home/* ]]; then
    echo "skipping privileged setup for the GDM session; it runs at first real login"
    exit 0
fi

pkexec /usr/bin/ublue-privileged-setup
