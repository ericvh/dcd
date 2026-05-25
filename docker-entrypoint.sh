#!/bin/sh
set -e

sim="${DCD_SIM:-${DCD_SIMULATE:-}}"
case "$(printf '%s' "$sim" | tr '[:upper:]' '[:lower:]')" in
  1|true|yes|on) sim=1 ;;
  *) sim= ;;
esac

if [ -z "$sim" ]; then
  if [ ! -S /var/run/docker.sock ]; then
    echo "dcd: /var/run/docker.sock is not available." >&2
    echo "  Mount the host socket, e.g. -v /var/run/docker.sock:/var/run/docker.sock" >&2
    echo "  Or set DCD_SIM=true for a simulator-only container." >&2
    exit 1
  fi
fi

exec dcd "$@"
