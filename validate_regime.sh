#!/usr/bin/env bash
# validate_regime.sh — v2.2 — Layer-1 regime ops on 1-REPORTER (control box, no trading).
# v2.1 — 2026-07-14 — LAYOUT CONSOLIDATION: tape from ohlc/<date>/ (new
#        lowercase _ohlc_ names, legacy _OHLC_ accepted), replay jsonl + diary
#        under reports/. Logic unchanged.
# v2.2 — 2026-07-23 — DOC SYNC (header audit, no logic change): title synced to
#        the newest entry; removed the two RETIRED data/harvest paths from the
#        Data block (layout consolidated to ohlc/ + reports/ in v2.1;
#        migrate_data_layout.sh rmdir'd data/harvest — never recreate it).
#
# Single entrypoint for the MANUAL regime-validation workflow. Inert code library
# (~/options-trader-v3) + read-only replay over harvest's OHLC tape. No systemd, no
# credentials, no live path. Tape-only — never reads trades.
#
# Data (authoritative, per day_trader_pro/harvest.py):
#     ~/day_trader_pro/ohlc/<date>/<SYM>_ohlc_<date>.csv               (tape in)
#     ~/day_trader_pro/reports/  — replay jsonl + rolling diary        (products out)
#
# Subcommands:
#     ./validate_regime.sh                 # run TODAY: pull, replay, append diary
#     ./validate_regime.sh 2026-07-13      # run a specific date (+ diary)
#     ./validate_regime.sh --report [date] # reprint a SAVED report (no re-run); default=today
#     ./validate_regime.sh --diary         # view the whole rolling diary
#     ./validate_regime.sh --backfill      # fill every diary gap that has tape on disk
#     ./validate_regime.sh --backfill --rebuild   # re-score every dated tape
#
# First run auto-bootstraps the checkout + venv (pandas/numpy/pytz only — no SDK).
set -uo pipefail

REPO_URL="https://github.com/TX-9AI/options_trader_v3.git";
REPO_DIR="$HOME/options-trader-v3";
VENV="$REPO_DIR/venv";
PY="$VENV/bin/python";
HARVEST="$HOME/day_trader_pro/ohlc";           # v2.1: consolidated tape root
DIARY_DIR="$HOME/day_trader_pro/reports";      # v2.1: all aggregates live here

ensure_env() {
  if [ ! -d "$REPO_DIR/.git" ]; then
    echo "[setup] cloning $REPO_URL -> $REPO_DIR";
    git clone "$REPO_URL" "$REPO_DIR" || { echo "clone failed"; exit 1; };
  fi;
  if [ ! -x "$PY" ]; then
    echo "[setup] creating venv + pandas numpy pytz (no SDK)";
    python3 -m venv "$VENV" || { echo "venv create failed"; exit 1; };
    "$VENV/bin/pip" install --quiet --upgrade pip;
    "$VENV/bin/pip" install --quiet pandas numpy pytz || { echo "pip install failed"; exit 1; };
  fi;
  cd "$REPO_DIR" || { echo "cannot cd $REPO_DIR"; exit 1; };
}

do_pull() { echo "[pull] git pull --ff-only"; git pull --ff-only || echo "[pull] warn: pull failed, using existing checkout"; }

# replay one date's tape + append its diary row
run_date() {
  local D="$1"; local DAY="$HARVEST/$D";
  if [ ! -d "$DAY" ]; then echo "no harvest folder for $D at $DAY (has harvest.py run?)"; return 1; fi;
  local N; N="$(ls "$DAY"/*_ohlc_*.csv "$DAY"/*_OHLC_*.csv 2>/dev/null | wc -l)";
  if [ "$N" -eq 0 ]; then echo "no *_ohlc_*.csv in $DAY"; return 1; fi;
  local LOG="$DIARY_DIR/regime_replay_$D.jsonl"; mkdir -p "$DIARY_DIR";
  echo "[replay] $D: $N symbol CSVs -> scoring through real engines (--no-v13)";
  "$PY" -m tests.replay_confluence "$DAY" --no-v13 --jsonl "$LOG";
  local RC=$?;
  if [ "$RC" -eq 0 ] || [ "$RC" -eq 2 ]; then
    echo "[diary] upserting $D";
    "$PY" -m tests.regime_diary --log "$LOG" --diary-dir "$DIARY_DIR";
  else
    echo "[diary] skipped ($D replay rc=$RC)";
  fi;
  return $RC;
}

# ---- dispatch ----
case "${1:-}" in
  --report)
    ensure_env;
    D="${2:-$(TZ=America/New_York date +%F)}";
    LOG="$DIARY_DIR/regime_replay_$D.jsonl";
    if [ ! -f "$LOG" ]; then echo "no saved report for $D at $LOG — run a replay for $D first"; exit 1; fi;
    "$PY" -m tests.replay_confluence --report-only "$LOG";
    ;;
  --diary)
    ensure_env;
    "$PY" -m tests.regime_diary --view --diary-dir "$DIARY_DIR";
    ;;
  --backfill)
    ensure_env; do_pull;
    if [ "${2:-}" = "--rebuild" ]; then
      echo "[backfill] REBUILD: re-scoring every dated tape";
      "$PY" -m tests.regime_backfill --harvest "$HARVEST" --diary-dir "$DIARY_DIR" --reports "$DIARY_DIR" --rebuild;
    else
      echo "[backfill] filling diary gaps that have tape on disk";
      "$PY" -m tests.regime_backfill --harvest "$HARVEST" --diary-dir "$DIARY_DIR" --reports "$DIARY_DIR";
    fi;
    ;;
  [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9])
    ensure_env; do_pull; run_date "$1"; exit $?;
    ;;
  "")
    ensure_env; do_pull; run_date "$(TZ=America/New_York date +%F)"; exit $?;
    ;;
  *)
    echo "usage: ./validate_regime.sh [YYYY-MM-DD | --report [date] | --diary | --backfill [--rebuild]]";
    exit 2;
    ;;
esac
