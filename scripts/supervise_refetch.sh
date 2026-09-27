#!/bin/bash
# Runs scripts/refetch_expose_text.py under a hard OS-level `timeout`,
# restarting it automatically on ANY exit -- crash, natural completion, or a
# hang. Needed because the script has hung silently multiple times (0% CPU,
# sleeping in ep_poll, zero progress for 46+ minutes) in a way that its own
# internal asyncio.wait_for watchdogs did not resolve -- likely an orphaned
# grandchild process (a headless browser's own subprocess) holding a pipe
# open that the asyncio event loop is waiting to read from, which in-process
# cancellation cannot force closed. `timeout --signal=KILL` kills the whole
# thing from outside instead.
#
# Stops when: the checkpoint file (data/.refetch_progress.json) is gone
# (refetch_expose_text.py deletes it on full completion), or after 3
# consecutive restarts produce zero new progress (a real stall, not a
# transient hang -- needs a human).
set -uo pipefail
cd /tmp/property-investment-finder

get_done() {
  /home/vincent/laya_venv/bin/python -c "
import json, os
p = 'data/.refetch_progress.json'
print(len(json.load(open(p))) if os.path.exists(p) else -1)
"
}

stall_count=0
while true; do
  before=$(get_done)
  if [ "$before" = "-1" ]; then
    echo "$(date -u +%FT%TZ) supervisor: no checkpoint file -- refetch already complete"
    exit 0
  fi
  echo "$(date -u +%FT%TZ) supervisor: launching refetch_expose_text.py (done so far: $before/364)"
  timeout --signal=KILL 300 /home/vincent/multica-lab/venv-scrape/bin/python scripts/refetch_expose_text.py
  rc=$?
  after=$(get_done)
  echo "$(date -u +%FT%TZ) supervisor: exited rc=$rc, done now: $after/364"

  if [ "$after" = "-1" ]; then
    echo "$(date -u +%FT%TZ) supervisor: complete!"
    exit 0
  fi
  if [ "$after" = "$before" ]; then
    stall_count=$((stall_count + 1))
    echo "$(date -u +%FT%TZ) supervisor: no progress this attempt (stall_count=$stall_count)"
  else
    stall_count=0
  fi
  if [ "$stall_count" -ge 3 ]; then
    echo "$(date -u +%FT%TZ) supervisor: 3 consecutive restarts with zero progress -- stopping, needs attention"
    exit 1
  fi
done
