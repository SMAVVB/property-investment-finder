#!/bin/bash
# Runs the refetch under scripts/supervise_refetch.sh (auto-restarts on any
# hang/crash, hard-killed externally via `timeout` -- see that script for
# why), then regenerates financials/judgments/shortlist and commits+pushes
# the result. Meant to survive unattended after the user reboots this
# machine into Windows and back.
set -e
cd /tmp/property-investment-finder

while pgrep -f "scripts/refetch_expose_text.py" > /dev/null; do
  sleep 10
done

./scripts/supervise_refetch.sh

/home/vincent/laya_venv/bin/python run_v1_pipeline.py --judge finetuned

git add data/listings.db data/v1_shortlist.md
git commit -m "$(cat <<'EOF'
Regenerate shortlist on corrected expose text (multi-section fix)

All 364 listings' raw_data re-fetched with the fixed extraction (captures
every expose-description-body section, not just the first) after the user
found is24-167951332's real risk disclosure (sitting tenant on below-market
rent, end-of-life electrics) was silently missing from raw_data.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_011mDK3TmcgpPLGPpzCaGB93
EOF
)"
git push origin main

echo "FINISH_REFETCH_AND_REGEN: done at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
