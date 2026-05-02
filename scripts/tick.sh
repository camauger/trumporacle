#!/usr/bin/env bash
# Wrapper for Windows Task Scheduler: cd to project + run mvp-tick + log.
# Auto-localizes via BASH_SOURCE so the project path (with accents) never
# needs to be hardcoded.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG="${TRUMPORACLE_TICK_LOG:-$HOME/trumporacle-tick.log}"

{
  printf '\n=== %s tick start (pid %d) ===\n' "$(date -u +%FT%TZ)" "$$"
  cd "$PROJECT_DIR"
  just mvp-tick
  printf '=== %s tick end ===\n' "$(date -u +%FT%TZ)"
} >> "$LOG" 2>&1
