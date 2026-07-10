#!/usr/bin/env bash
# open beryl (optionally on urls):  beryl.sh [url...]
# a second launch hands its urls to the running instance over the local socket
# and exits, so this is always safe to spam from binds.
export PYTHONPATH="$(dirname "$(readlink -f "$0")")${PYTHONPATH:+:$PYTHONPATH}"
setsid -f python -m beryl "$@" >/dev/null 2>&1
