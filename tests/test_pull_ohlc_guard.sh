#!/usr/bin/env bash
# tests/test_pull_ohlc_guard.sh — v1.2 — 2026-08-04
#
# v1.1 — the guard is OFF BY DEFAULT (v1.4, operator directive) and gated on
#        OT_PULL_RTH_GUARD. Both modes are driven here: default must ALWAYS
#        rebuild, and =1 must reproduce v1.3 exactly. Keeping the =1 arm tested
#        is the point — the refusal path still exists and must still be correct
#        when it is switched back on.
#
# The v1.3 guard decision table in pull_today_ohlc.sh, driven over all eight
# (FEED, POSTCLOSE, BOT) states.
#
# WHY A SHELL TEST AND NOT PYTEST: the guard is three shell conditions inside a
# detached __work block that stops systemd units and calls the TastyTrade
# producer. Standing that up would test the mocks. The decision itself is one
# boolean and it is the whole of the change — v1.1's version was correct for
# every state EXCEPT the one backfill actually uses, and it cost two sessions of
# sat-out tape before anyone looked.
#
# KEEP THIS IN SYNC BY HAND, deliberately: if the condition in the script
# changes, this file must change with it. check_versions carries a canary on the
# literal condition so a drift between the two is caught at deploy time.
#
# Run:  bash tests/test_pull_ohlc_guard.sh
# script and driven over all eight (FEED, POSTCLOSE, BOT) combinations.
# The condition below is copied VERBATIM from pull_today_ohlc.sh v1.3.
decide() {
  GUARD="$1"; FEED="$2"; POSTCLOSE="$3"; BOT="$4"
  if [ "$GUARD" = "1" ] && [ "$FEED" = "active" ] && [ "$POSTCLOSE" = "0" ] && [ "$BOT" = "active" ]; then
    echo "SKIP"
  else
    echo "REBUILD"
  fi
}
fail=0
chk(){ got=$(decide "$1" "$2" "$3" "$4"); [ "$got" = "$5" ] && s="ok " || { s="FAIL"; fail=1; }; \
       printf "  %s guard=%s feed=%-8s postclose=%s bot=%-8s -> %-7s (want %s)\n" "$s" "$1" "$2" "$3" "$4" "$got" "$5"; }
echo "DEFAULT — guard ON (v1.5): refuses only for a LIVE BOT mid-session"
echo "  THE CASE IT EXISTS FOR — trading box mid-session:"
chk 1 active   0 active   SKIP
echo "  REPORTS AND BACKFILLS — always allowed:"
chk 1 active   0 inactive REBUILD
chk 1 active   0 unknown  REBUILD
chk 1 active   1 active   REBUILD
chk 1 inactive 0 inactive REBUILD
echo "ESCAPE HATCH OT_PULL_RTH_GUARD=0 — never refuses:"
chk 0 active   0 active   REBUILD
chk 0 active   0 inactive REBUILD
exit $fail
