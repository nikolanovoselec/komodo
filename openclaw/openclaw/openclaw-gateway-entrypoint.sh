#!/bin/sh
set -eu

node dist/index.js config set gateway.auth.mode none

exec node dist/index.js gateway --bind lan --port 18789
