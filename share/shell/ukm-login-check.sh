#!/usr/bin/env sh
# ukm login-time kernel update check
#
# Source this file from ~/.bashrc, ~/.zshrc, or ~/.profile to get a
# one-line notification when a newer kernel is available.
#
# Installation (automatic):
#   ukm notify-shell-install
#
# Installation (manual):
#   echo '. /path/to/ukm-login-check.sh' >> ~/.bashrc
#
# The check runs at most once per login session (guarded by UKM_CHECKED)
# and only when the shell is interactive, so it never slows down scripts.
#
# For background checks every 12 hours, use the systemd timer instead:
#   ukm notify-enable

# Only run once per session and only in interactive shells
[ -z "$PS1" ] && return 0
[ -n "$UKM_CHECKED" ] && return 0
export UKM_CHECKED=1

# Require ukm to be on PATH
command -v ukm >/dev/null 2>&1 || return 0

# Run the check in the background so it never blocks the prompt.
# Output is suppressed; notify-send (if available) will pop a desktop
# notification. The exit code is ignored.
(ukm notify --provider=mainline_ppa >/dev/null 2>&1 &)
