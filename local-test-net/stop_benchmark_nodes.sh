#!/bin/bash
# Stop all benchmark nodes by inspecting prod-local/ for genesis and join* directories.

for dir in prod-local/*/; do
  [ -d "$dir" ] || continue
  name="$(basename "$dir")"
  case "$name" in
    genesis|join*)
      echo "Stopping $name"
      docker compose -p "$name" down
      ;;
  esac
done
