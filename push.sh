#!/bin/bash
# =============================================================================
# push.sh — Vertigo Capital Git Push / Deploy Tool
# v3.0 — 2026-06-27 — initial release
# v1.1 — 2026-06-27 — add rebase pull before push, fix success check, exclude WAL files
# v1.2 — 2026-06-30 — auto-detect and repair doubled/malformed remote URLs
# v1.3 — 2026-06-30 — handle diverged/unrelated history cleanly (force-push prompt)
# v1.4 — 2026-07-02 — normalize the executable bit on all tracked .sh files
# v1.5 — 2026-07-02 — set git author to the repo owner (TX-9AI)
# v1.6 — 2026-07-06 — add DOWNLOAD direction so fleet can wake a box and deploy:
#         `push.sh --deploy` (alias --pull) fetches origin and hard-resets THIS
#         bot to the remote branch, repairs .sh +x, restarts the service, and
#         verifies it. `--no-restart` skips the restart. Default (no flag) is the
#         original upload: commit local changes and push to GitHub.
#         Unattended-safe: per-bot config is in the systemd env; runtime state
#         (trades.db, bot.log, orb_state.json, orb_range.json) is untracked and
#         is NOT touched by `git reset --hard`.
# v3.1 — 2026-07-10 — derive REPO from the remote URL instead of hardcoding
#         options_trader_v2. The v3.0 header bump left the detection pinned to
#         v2, so a box repointed to v3 would get dragged back to v2 on the next
#         deploy/push. REPO is now parsed from origin (token- and .git-safe),
#         so v2/v3/future all resolve correctly. SERVICE still keyed by family.
# v3.0 — 2026-07-10 — repo-wide v3.0 bump: Yahoo-Finance purge & data stream
#         mapping optimization (single shared TastyTrade candle feed). No
#         logic change in this file.
#
# Usage:
#   bash push.sh                        — commit local changes & push to GitHub
#   bash push.sh "your commit message"  — push with a custom message
#   bash push.sh --deploy               — fetch + reset --hard + restart (pull side)
#   bash push.sh --deploy --no-restart  — deploy without restarting the service
# v1.9 — 2026-07-30 — the v1.8 refusal told you to `pip install pyflakes`, which
#         provisions one tool by hand and leaves the next one to be discovered
#         the same way. It now points at install_tooling.sh, which installs the
#         repo's own requirements into whatever python is active — venv if the
#         checkout is a full setup_ec2.sh install, system python if it is a bare
#         clone. Every bot here runs independently of any controller, so the repo
#         has to be able to provision itself wherever it lands.
# v1.8 — 2026-07-30 — UNDEFINED-NAME GATE before commit. The box-side deploy
#         check is `python -c "import ast"`, which proves a file COMPILES; an
#         undefined name compiles fine and raises at RUNTIME, so the deploy path
#         could not see the class that cost two sessions in two days —
#         continuation `mid` (07-29, whole ORB window, all 15 boxes) and
#         butterfly `_mult` (07-30, IWM crash-loop, regime-gated so 14 boxes ran
#         it clean). pyflakes now runs over the tracked *.py set and REFUSES the
#         commit on any "undefined name". Missing pyflakes is a REFUSAL, never a
#         skip. PUSH_SKIP_LINT=1 overrides, loudly.
# v1.7 — 2026-07-30 — TARGET RESOLUTION: prefer the caller's directory over the
#         $HOME scan, and ANNOUNCE the resolved target + remote before acting.
#         The old block ignored $PWD entirely and took the first $HOME entry
#         containing main.py+config.py — invisible on a bot box (one bot per
#         home), wrong on the control server. Run from ~/options-trader-v3 with
#         a futures_trader_v1 checkout present, it cd'd into FUTURES and refused
#         with a message naming the wrong project's remote; refusing was luck,
#         since a successful push would have written options_trader files into
#         the futures repo. Order is now: exported $BOT_DIR -> $PWD if it looks
#         like a bot checkout -> $HOME scan (with a loud warning when the
#         fallback is what resolved it). Prerequisite for the nested-module
#         layout in docs/ARCHITECTURE.md, where the scan becomes ambiguous by
#         construction rather than by accident.
# =============================================================================

BOLD='\033[1m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'
YELLOW='\033[1;33m'; RED='\033[0;31m'; RESET='\033[0m'

# ── Parse flags (leave any commit message as the remaining positional arg) ────
MODE="push"; RESTART=true; ARGS=()
for a in "$@"; do
    case "$a" in
        --deploy|--pull) MODE="deploy" ;;
        --no-restart)    RESTART=false ;;
        *)               ARGS+=("$a") ;;
    esac
done
set -- "${ARGS[@]}"

echo ""
echo -e "${BOLD}${CYAN}╔══════════════════════════════════════════════════════╗${RESET}"
if [ "$MODE" = "deploy" ]; then
    echo -e "${BOLD}${CYAN}║     Vertigo Capital — Git Deploy (pull)             ║${RESET}"
else
    echo -e "${BOLD}${CYAN}║     Vertigo Capital — Git Push                      ║${RESET}"
fi
echo -e "${BOLD}${CYAN}╚══════════════════════════════════════════════════════╝${RESET}"
echo ""

# ── Detect which bot and repo ─────────────────────────────────────────────────
# v1.7 — PREFER THE CALLER'S DIRECTORY. This block used to go straight to the
# $HOME scan below, ignoring where it was invoked from. On a bot box that is
# invisible (one bot per $HOME); on the CONTROL server it picks whichever
# project sorts first. On 2026-07-29, run from ~/options-trader-v3 with a
# futures_trader_v1 checkout also present, it cd'd into FUTURES and refused
# with "Could not detect repo from git remote" — naming the wrong project's
# remote. Refusing was lucky: a successful push would have written
# options_trader files into the futures repo.
#
# It also has to be fixed BEFORE the nested-module layout in
# docs/ARCHITECTURE.md, because once market_brief/ and options_trader/ share a
# parent the scan is ambiguous by construction, not just by accident.
#
# Resolution order: an explicit $BOT_DIR override -> the current directory when
# it looks like a bot checkout -> the $HOME scan as a last resort.
_looks_like_bot() {   # $1 = dir
    [ -f "${1}/main.py" ] && [ -f "${1}/config.py" ]
}

BOT_DIR="${BOT_DIR:-}"          # honour an explicit override if one is exported
HOW=""
INVOKED_FROM="$PWD"             # captured BEFORE the cd below, or the warning
                                # at the end can never fire (it would be
                                # comparing $PWD to itself)
if [ -n "$BOT_DIR" ] && _looks_like_bot "$BOT_DIR"; then
    HOW="\$BOT_DIR override"
elif _looks_like_bot "$PWD"; then
    BOT_DIR="$PWD"; HOW="current directory"
else
    for dir in "$HOME"/*/; do
        [[ "$dir" == *"-deploy"* ]] && continue
        if [ -f "${dir}main.py" ] && [ -f "${dir}config.py" ]; then
            BOT_DIR="${dir%/}"; HOW="\$HOME scan"
            break
        fi
    done
fi

if [ -z "$BOT_DIR" ]; then
    echo -e "${YELLOW}  ⚠  Could not detect bot directory. Run from a bot"
    echo -e "     checkout (one containing main.py and config.py), or export"
    echo -e "     BOT_DIR=/path/to/checkout.${RESET}"
    exit 1
fi
cd "$BOT_DIR" || exit 1

# SAY WHICH PROJECT WE PICKED, ALWAYS. The 07-29 incident was survivable only
# because the remote mismatch happened to trip a guard; the operator had no way
# to know the script had silently changed directory. Announce it before acting.
echo -e "  ${CYAN}target:${RESET} $BOT_DIR  ${CYAN}(via ${HOW})${RESET}"
echo -e "  ${CYAN}remote:${RESET} $(git remote get-url origin 2>/dev/null || echo '(none)')"
if [ "$HOW" = "\$HOME scan" ] && [ "$INVOKED_FROM" != "$BOT_DIR" ]; then
    echo -e "  ${YELLOW}⚠  invoked from $INVOKED_FROM, which is not a bot"
    echo -e "     checkout — fell back to scanning \$HOME. VERIFY the target"
    echo -e "     above is the project you meant.${RESET}"
fi
echo ""

# ── If a previous run left a rebase in progress, clear it before continuing ──
if [ -d ".git/rebase-merge" ] || [ -d ".git/rebase-apply" ]; then
    echo -e "  ${YELLOW}⚠  Found an in-progress rebase from a previous run — aborting it.${RESET}"
    git rebase --abort 2>/dev/null || true
    echo ""
fi

# ── Repair a malformed remote URL if present ──────────────────────────────────
CURRENT_REMOTE_RAW=$(git remote get-url origin 2>/dev/null || echo "")
if echo "$CURRENT_REMOTE_RAW" | grep -qE 'github\.com/.*github\.com/'; then
    echo -e "  ${YELLOW}⚠  Detected malformed remote URL — repairing...${RESET}"
    FIXED_PATH=$(echo "$CURRENT_REMOTE_RAW" | sed -E 's#.*github\.com/##')
    FIXED_PATH="${FIXED_PATH%.git}"
    FIXED_PATH="${FIXED_PATH%/}"
    git remote set-url origin "https://github.com/${FIXED_PATH}.git"
    echo -e "  ${GREEN}✓  Remote repaired: https://github.com/${FIXED_PATH}.git${RESET}"
    echo ""
fi

# Read current remote URL to determine repo (after any repair above)
CURRENT_REMOTE=$(git remote get-url origin 2>/dev/null || echo "")
if echo "$CURRENT_REMOTE" | grep -q "crypto_trader"; then
    SERVICE="cryptobot"
elif echo "$CURRENT_REMOTE" | grep -q "options_trader"; then
    SERVICE="optionsbot"
else
    echo -e "${YELLOW}  ⚠  Could not detect repo from git remote. Is git initialized?${RESET}"
    echo "  Current remote: $CURRENT_REMOTE"
    exit 1
fi

# Derive the repo name from the actual remote (token-safe, .git-safe) so this
# script tracks whatever repo the box points at — v2, v3, or beyond — with no
# per-version edits. This is the fix for the old hardcoded REPO="options_trader_v2"
# that would silently drag a repointed box back to v2 on the next deploy.
REPO=$(echo "$CURRENT_REMOTE" | sed -E 's#.*github\.com[:/]+[^/]+/([^/.]+).*#\1#')
if [ -z "$REPO" ] || [ "$REPO" = "$CURRENT_REMOTE" ]; then
    echo -e "${YELLOW}  ⚠  Could not parse repo name from remote: $CURRENT_REMOTE${RESET}"
    exit 1
fi

BRANCH=$(git symbolic-ref --short HEAD 2>/dev/null || echo "main")
CLEAN_URL="https://github.com/TX-9AI/${REPO}.git"

echo -e "  Bot dir: ${BOLD}${BOT_DIR}${RESET}"
echo -e "  Repo:    ${BOLD}https://github.com/TX-9AI/${REPO}${RESET} (${BRANCH})"
echo -e "  Service: ${BOLD}${SERVICE}${RESET}"
echo ""

# ══════════════════════════════════════════════════════════════════════════════
# DEPLOY (pull) — fetch + hard-reset this bot to origin, repair perms, restart
# ══════════════════════════════════════════════════════════════════════════════
if [ "$MODE" = "deploy" ]; then
    # Token only needed for a private repo — inject for the fetch, then restore.
    TOKEN=$(sudo systemctl show "$SERVICE" --property=Environment 2>/dev/null \
        | grep -o 'GITHUB_TOKEN=[^ ]*' | cut -d= -f2)
    [ -n "$TOKEN" ] && git remote set-url origin \
        "https://TX-9AI:${TOKEN}@github.com/TX-9AI/${REPO}.git"

    echo "  Fetching origin/${BRANCH}…"
    if ! git fetch origin "$BRANCH" --quiet; then
        git remote set-url origin "$CLEAN_URL"
        echo -e "  ${RED}⚠  Fetch failed — check network/token.${RESET}"
        exit 1
    fi

    OLD_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "?")
    git reset --hard "origin/${BRANCH}" >/dev/null
    git remote set-url origin "$CLEAN_URL"          # always restore token-free URL
    git ls-files '*.sh' | xargs -r chmod +x 2>/dev/null || true
    NEW_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "?")

    if [ "$OLD_SHA" = "$NEW_SHA" ]; then
        echo -e "  ${GREEN}Already up to date${RESET} @ ${NEW_SHA}"
    else
        echo -e "  ${GREEN}Updated${RESET} ${OLD_SHA} → ${BOLD}${NEW_SHA}${RESET}"
    fi

    if [ "$RESTART" = true ]; then
        echo "  Restarting ${SERVICE}…"
        sudo systemctl restart "$SERVICE"
        sleep 3
        STATE=$(systemctl is-active "$SERVICE" 2>/dev/null)
        if [ "$STATE" = "active" ]; then
            echo -e "  ${GREEN}✅ ${SERVICE} active${RESET} @ ${NEW_SHA}"
        else
            echo -e "  ${RED}🚨 ${SERVICE} ${STATE}${RESET} — journalctl -u ${SERVICE} -n 20"
            exit 1
        fi
    else
        echo -e "  ${YELLOW}(service not restarted — --no-restart)${RESET}"
    fi
    echo ""
    exit 0
fi

# ══════════════════════════════════════════════════════════════════════════════
# PUSH (upload) — original behavior: commit local changes and push to GitHub
# ══════════════════════════════════════════════════════════════════════════════

# ── Author commits as the repo owner, not the ubuntu system user ──────────────
GH_OWNER=$(echo "$CURRENT_REMOTE" | sed -E 's#.*github\.com[:/]+([^/]+)/.*#\1#')
if [ -n "$GH_OWNER" ] && [ "$GH_OWNER" != "$CURRENT_REMOTE" ]; then
    git config user.name  "$GH_OWNER"
    git config user.email "${GH_OWNER}@users.noreply.github.com"
fi

# ── Get GitHub token ──────────────────────────────────────────────────────────
TOKEN=$(sudo systemctl show "$SERVICE" --property=Environment 2>/dev/null \
    | grep -o 'GITHUB_TOKEN=[^ ]*' | cut -d= -f2)

if [ -z "$TOKEN" ]; then
    echo -e "  ${YELLOW}GITHUB_TOKEN not in systemd environment.${RESET}"
    read -rsp "  GitHub personal access token: " TOKEN
    echo ""
fi

if [ -z "$TOKEN" ]; then
    echo -e "  ${YELLOW}⚠  No token provided. Aborting.${RESET}"
    exit 1
fi

# ── Ensure WAL files are ignored ─────────────────────────────────────────────
GITIGNORE="$BOT_DIR/.gitignore"
for pattern in "trades.db-shm" "trades.db-wal" "*.db-shm" "*.db-wal"; do
    grep -qF "$pattern" "$GITIGNORE" 2>/dev/null || echo "$pattern" >> "$GITIGNORE"
done

# ── Keep shell scripts executable ─────────────────────────────────────────────
git ls-files '*.sh' | xargs -r chmod +x 2>/dev/null || true

# Check for changes
HAS_CHANGES=true
if git diff --quiet && git diff --cached --quiet && [ -z "$(git ls-files --others --exclude-standard)" ]; then
    HAS_CHANGES=false
fi

if [ "$HAS_CHANGES" = true ]; then
    echo "  Staged changes:"
    git status --short
    echo ""

    # ── v1.8 UNDEFINED-NAME GATE — the last moment a NameError is free ────────
    # The box-side deploy gate is `python -c "import ast"` (working agreement,
    # after repeated wrong-venv/no-pytest burns). ast.parse proves a file
    # COMPILES — and an undefined name compiles fine, because it is a RUNTIME
    # error. So the deploy path was structurally blind to the class that cost two
    # sessions in two days:
    #   2026-07-29  continuation `mid` — orphaned after the FVG rewire. NameError
    #               every tick; all 15 boxes took ZERO trades until 10:05 ET.
    #   2026-07-30  butterfly `_mult` — orphaned after the 1x-EM revert.
    #               Regime-gated, so ONLY a box in COMPRESSION reached it: IWM
    #               crash-looped for an hour while 14 boxes ran it clean.
    # Both are found by static analysis in under a second. This runs here because
    # push.sh is the chokepoint every deploy already passes through, and control
    # is the last place the fix costs nothing.
    if [ "${PUSH_SKIP_LINT:-0}" = "1" ]; then
        echo -e "  ${YELLOW}⚠  PUSH_SKIP_LINT=1 — undefined-name gate BYPASSED."
        echo -e "     Two production outages in two days came from this class.${RESET}"
    else
        LINT_PY="$(command -v python3 || command -v python)"
        if [ -z "$LINT_PY" ] || ! "$LINT_PY" -m pyflakes --version >/dev/null 2>&1; then
            echo -e "  ${RED}✗  pyflakes is not available — the undefined-name gate"
            echo -e "     CANNOT RUN, so this push is refused. Provision the"
            echo -e "     checkout (works with or without a controller):"
            echo -e "       bash $BOT_DIR/install_tooling.sh"
            echo -e "     (Override with PUSH_SKIP_LINT=1 if you accept the risk.)"
            echo -e "     A silently skipped guard is the exact failure mode this"
            echo -e "     gate exists to prevent.${RESET}"
            exit 1
        fi
        UNDEF="$("$LINT_PY" -m pyflakes $(git ls-files '*.py') 2>/dev/null \
                 | grep -i 'undefined name' || true)"
        if [ -n "$UNDEF" ]; then
            echo -e "  ${RED}✗  UNDEFINED NAME(S) — refusing to commit or push.${RESET}"
            echo "$UNDEF" | sed 's/^/       /'
            echo -e "  ${YELLOW}     This is the 07-29 'mid' / 07-30 '_mult' defect class."
            echo -e "     It compiles, passes the box-side ast gate, and raises at"
            echo -e "     runtime on whatever path reaches it.${RESET}"
            exit 1
        fi
        echo -e "  ${GREEN}✓  undefined-name gate: clean${RESET}"
    fi

    COMMIT_MSG="${1:-$(date '+%Y-%m-%d') — patch update}"
    git add .
    git ls-files '*.sh' | xargs -r git update-index --chmod=+x 2>/dev/null || true
    git commit -m "$COMMIT_MSG"
else
    echo -e "  ${GREEN}Nothing new to commit — checking if push is still needed.${RESET}"
fi

# ── Push with token ────────────────────────────────────────────────────────────
git remote set-url origin "https://TX-9AI:${TOKEN}@github.com/TX-9AI/${REPO}.git"

PULL_OUTPUT=$(git pull --rebase origin "$BRANCH" 2>&1)
PULL_STATUS=$?

if [ $PULL_STATUS -ne 0 ] || [ -d ".git/rebase-merge" ] || [ -d ".git/rebase-apply" ]; then
    git rebase --abort 2>/dev/null || true
    echo ""
    echo -e "  ${YELLOW}⚠  Remote history has diverged from this server's local history.${RESET}"
    echo ""
    echo "  Options:"
    echo "    1) Force-push THIS SERVER's files as the new GitHub state (overwrites GitHub)"
    echo "    2) Cancel — resolve manually"
    echo ""
    read -rp "  Choice [1/2]: " CHOICE
    if [ "$CHOICE" = "1" ]; then
        if git push origin "$BRANCH" --force; then
            git remote set-url origin "$CLEAN_URL"
            echo ""
            echo -e "  ${GREEN}✅ Force-pushed local state to ${REPO} (${BRANCH}).${RESET}"
            echo -e "  ${YELLOW}     Other servers: fleet.py update  (runs push.sh --deploy)${RESET}"
        else
            git remote set-url origin "$CLEAN_URL"
            echo -e "  ${RED}⚠  Force push failed — check errors above.${RESET}"
            exit 1
        fi
    else
        git remote set-url origin "$CLEAN_URL"
        echo -e "  ${YELLOW}Cancelled. No changes pushed.${RESET}"
        exit 1
    fi
else
    if git push origin "$BRANCH"; then
        git remote set-url origin "$CLEAN_URL"
        echo ""
        echo -e "  ${GREEN}✅ Pushed to ${REPO} (${BRANCH}) successfully.${RESET}"
    else
        git remote set-url origin "$CLEAN_URL"
        echo -e "  ${YELLOW}⚠  Push failed — check errors above.${RESET}"
        exit 1
    fi
fi
echo ""
