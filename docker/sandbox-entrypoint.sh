#!/bin/sh
set -eu

test -d /project-ro
test -d /workspace
cp -a /project-ro/. /workspace/

if test -n "${SANDBOX_NODE_MODULES:-}"; then
    mkdir /workspace/node_modules
    mkdir /workspace/.sandbox-tmp
    TMPDIR=/workspace/.sandbox-tmp
    export TMPDIR
    for entry in "$SANDBOX_NODE_MODULES"/* "$SANDBOX_NODE_MODULES"/.[!.]* "$SANDBOX_NODE_MODULES"/..?*; do
        if test ! -e "$entry" && test ! -L "$entry"; then
            continue
        fi
        ln -s "$entry" "/workspace/node_modules/$(basename "$entry")"
    done
fi

cd /workspace
exec "$@"
