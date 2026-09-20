#!/bin/bash
# Classify ALL remaining human-grounded claims in resumable 2000-claim batches.
# Each batch persists on completion, so a crash loses at most one batch.
# Safe to kill and relaunch: the CLI skips already-classified claims.
set -u
cd /Users/danielkliewer/Projects/ganymede2
export DATABASE_URL=postgresql+asyncpg://ganymede:ganymede@localhost:5432/ganymede
LOG=/tmp/voice_classify_full.log
BATCH=2000
MAX_BATCHES=40

for i in $(seq 1 $MAX_BATCHES); do
  echo "=== batch $i start $(date '+%H:%M:%S') ===" >> "$LOG"
  OUT=$(.venv/bin/python -m engine.cli classify-voices --model qwen3:8b --limit $BATCH --status SUPPORTED,VALIDATED,CONTESTED,CONTRADICTED 2>&1)
  echo "$OUT" >> "$LOG"
  if echo "$OUT" | grep -q "No unclassified"; then
    echo "=== ALL DONE $(date) ===" >> "$LOG"
    exit 0
  fi
  if echo "$OUT" | grep -qE "no valid classifications|No inference provider"; then
    echo "=== STALLED (check Ollama) $(date) ===" >> "$LOG"
    exit 1
  fi
done
echo "=== MAX BATCHES REACHED $(date) ===" >> "$LOG"
