#!/usr/bin/env python3
# tests/readiness_digest.py — options_trader_v3 — v1.4
# v1.4 — 2026-08-10 — THE ANTICIPATION BLOCK WAS PAIRING EVERY FIRE WITH THE
#         WRONG ARM. It read `armed_since[(sym, key)]`, the LIVE arm tracker:
#         by the time dispositions are processed it holds only the arms still
#         OPEN at end of day, one value per key. Every fire for a symbol got the
#         same, final arm time. On 2026-08-10 that printed nineteen GLD rows all
#         reading "armed 14:36 -> fired 10:07" — armed FOUR AND A HALF HOURS
#         AFTER the trade it claimed to anticipate.
#         ⚠️ IT SURVIVED BECAUSE IT LOOKED FINE: no error, no empty list, just a
#         plausible column of timestamps. The tell was the arithmetic, and only
#         when two columns were read against each other.
#         Now searches the CLOSED arm spans for the episode CONTAINING the fire,
#         else the most recent ending before it, and reports LEAD TIME. A fire
#         with no prior arm is COUNTED AND NAMED, not dropped — "fired without
#         ever arming" is a finding. The output states that a negative lead is
#         impossible, so the next instance announces itself.
# v1.2 — 2026-08-05 — THE HEADLINE COUNTED A DIFFERENT THING FROM THE LIST IT
#         POINTS AT. `npeg` measured peg rates on the RAW `_val` series while
#         FIT SUGGESTIONS measure the RAMPED output, so the number people read
#         could disagree with the suggestions it sends them to. The premise of
#         this whole section is about the RAMP — "a corroborator pegged at its
#         bound is a constant wearing new clothes" — and a RAW value at its
#         bound is frequently just what that factor is (a binary corroborator
#         is 0 or 1 by construction). 2026-08-05 reported "9 pegged factor(s)"
#         on the raw definition; the ramped count is what the Aug 8-9 fits
#         should be sized against. Now `npeg = len(fits)` — one definition,
#         and the wording says "pegged ramp(s)".
# v1.1 — 2026-07-28 — FACTOR CALIBRATION SECTION. v1.0 reported the machine
#         (states, R, arm episodes) but not the FACTORS, which is the same
#         omission ramp_calibration.py exists to prevent one layer down: a
#         corroborator pegged at its bound is a constant wearing new clothes,
#         and you cannot see that from R alone. Day one proved it — ten
#         symbols reported an identical r=0.65 because the conviction ramp
#         topped out below where the fleet actually lives. This section now
#         reports, per strategy per factor: percentiles of the RAW input and
#         peg rates on the RAMPED output, then prints a FIT SUGGESTION line
#         with the exact OT_TR_* export to try. Fitted, not guessed.
# v1.0 — 2026-07-27 — NEW. Nightly readiness digest (ROADMAP readiness track).
#
#   Offline control-server tool, stdlib-only, read-only. Reads the harvested
#   signal-journal jsonl for a date and digests the trade_readiness v1.1
#   events (`readiness`, `readiness_would_fire`, `readiness_staged_pick`) into
#   the DIAL-TUNING report: per strategy — time in each machine state, R
#   distribution, arm episodes and their durations, would-fire count,
#   staged-pick stats (target-delta and spread distributions, conv_ema vs the
#   bars), and — when `disposition` events exist in the same file — the
#   ANTICIPATION metric: for each fired trade, how long its strategy had been
#   ARMED beforehand (the lead-time the readiness engine exists to create).
#
#   Runs unattended as EOD-conductor phase 9 (--quiet prints ONE headline and
#   returns 0 even on empty nights so it can never mark the chain failed —
#   conditional_tables.py precedent). Writes:
#       reports/readiness_digest_<date>.txt
#       reports/readiness_digest_<date>.jsonl   (machine-readable, for tuning)
#
#   The bars it reports against are read FROM THE ROWS (each readiness row
#   embeds its bars), so a knob change on the boxes shows up here without
#   touching this tool.

from __future__ import annotations
import argparse, json, os, sys, glob
from datetime import datetime
from collections import defaultdict


# factor map: raw journal key -> (ramped key, OT_TR_ env stem, inverted?)
# "inverted" means the ramp output falls as the raw input rises (pull_val).
FACTOR_MAP = {
    "conv":      ("conv_val",  "CONV",     False),
    "dist_atr":  ("pull_val",  "PULL_ATR", True),
    "approach":  ("appr_val",  "APPROACH", False),
    "age_bars":  ("fresh_val", None,       True),
}
PEG_HI, PEG_LO = 0.95, 0.05
PEG_ALARM = 0.60          # >60% pegged = constant in new clothes (L1 convention)


def _pct(vals, q):
    if not vals:
        return 0.0
    s = sorted(vals)
    return s[min(int(q * len(s)), len(s) - 1)]


def _load_day(day_dir):
    rows = []
    for f in sorted(glob.glob(os.path.join(day_dir, "*.jsonl"))):
        sym = os.path.basename(f).split(".")[0].split("_")[0]
        try:
            with open(f) as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)
                    except Exception:
                        continue
                    r["_sym"] = sym
                    rows.append(r)
        except Exception:
            continue
    return rows


def digest(day_dir, date):
    rows = _load_day(day_dir)
    ready = [r for r in rows if r.get("event") in
             ("readiness", "readiness_would_fire") and "readiness" in r]
    picks = [r for r in rows if r.get("event") == "readiness_staged_pick"]
    disps = [r for r in rows if r.get("event") == "disposition"]

    per = defaultdict(lambda: {"rs": [], "machines": defaultdict(int),
                               "would_fire": 0, "arm_spans": [], "slopes": [],
                               "factors": defaultdict(list)})
    # arm episode tracking per (symbol, strategy)
    armed_since = {}
    for r in sorted(ready, key=lambda x: (x.get("_sym", ""), x.get("ts_et", ""))):
        d = r["readiness"]; key = d.get("strategy", "?")
        sym = r.get("_sym", "?"); ts = r.get("ts_et", "")
        p = per[key]
        p["rs"].append(float(d.get("r", 0.0)))
        p["slopes"].append(float(d.get("slope_per_min", 0.0)))
        for fk, fv in (d.get("factors") or {}).items():
            if isinstance(fv, (int, float)) and not isinstance(fv, bool):
                p["factors"][fk].append(float(fv))
        m = d.get("machine", "?"); p["machines"][m] += 1
        if r.get("event") == "readiness_would_fire":
            p["would_fire"] += 1
        ak = (sym, key)
        if m == "ARMED" and ak not in armed_since:
            armed_since[ak] = ts
        elif m != "ARMED" and ak in armed_since:
            p["arm_spans"].append((sym, armed_since.pop(ak), ts))

    # anticipation: disposition fires vs prior ARMED state of that strategy
    # ── v1.4 — ANTICIPATION PAIRED TO THE RIGHT ARM EPISODE ─────────────────
    # v1.3 read `armed_since[(sym, key)]`, which is the LIVE tracker: by the time
    # dispositions are processed it holds only the arms still OPEN at end of day,
    # and each key holds ONE value. So every fire for a symbol was stamped with
    # the same, final arm time — and on 2026-08-10 that printed 19 GLD rows all
    # reading "armed 14:36 -> fired 10:07", i.e. armed FOUR AND A HALF HOURS
    # AFTER the trade it supposedly anticipated. It rendered perfectly and meant
    # nothing, which is why it survived: no error, no empty output, just a
    # plausible-looking list.
    # Now: search the CLOSED arm spans for the episode that contains the fire,
    # or failing that the most recent one that ENDED before it, and report the
    # LEAD TIME. A fire with no prior arm is reported as such rather than
    # silently dropped — "the strategy fired without ever arming" is a finding,
    # not an absence.
    def _anticipation(sym, key, fire_ts):
        best, best_kind = None, None
        for s_sym, a_start, a_end in per[key]["arm_spans"]:
            if s_sym != sym:
                continue
            if a_start <= fire_ts <= a_end:
                return a_start, "armed-at-fire"      # exact: fired while ARMED
            if a_end < fire_ts and (best is None or a_end > best[1]):
                best, best_kind = (a_start, a_end), "armed-before"
        # an arm still open at EOD legitimately covers a late fire
        still = armed_since.get((sym, key))
        if still is not None and still <= fire_ts:
            if best is None or still > best[1]:
                return still, "armed-at-fire"
        return (best[0] if best else None), best_kind

    def _lead_min(a, b):
        try:
            return (datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds() / 60.0
        except Exception:                                     # noqa: BLE001
            return None

    anticipations = []
    for dp in disps:
        strat = str(dp.get("strategy") or dp.get("setup_type") or
                    (dp.get("signal") or {}).get("strategy") or "").lower()
        sym = dp.get("_sym", "?"); ts = dp.get("ts_et", "")
        for key in per:
            if key.split("_")[0] not in strat:
                continue
            armed_at, kind = _anticipation(sym, key, ts)
            lead = _lead_min(armed_at, ts) if armed_at else None
            anticipations.append({"sym": sym, "strategy": key,
                                  "armed_since": armed_at, "fired_at": ts,
                                  "kind": kind or "no-prior-arm",
                                  "lead_min": (round(lead, 1) if lead is not None else None)})

    pick_stats = defaultdict(lambda: {"n": 0, "deltas": [], "spreads": [], "convs": []})
    for r in picks:
        st = r.get("staged", {}); key = st.get("strategy", "?")
        ps = pick_stats[key]; ps["n"] += 1
        ps["deltas"].append(float(st.get("target_delta") or 0))
        ps["convs"].append(float(st.get("conv_ema") or 0))
        c = st.get("contract") or {}
        if c.get("spread_pct_of_mid") is not None:
            ps["spreads"].append(float(c["spread_pct_of_mid"]))

    lines = [f"READINESS DIGEST — {date}",
             f"journal rows: {len(rows)}  readiness: {len(ready)}  "
             f"staged picks: {len(picks)}  dispositions: {len(disps)}", ""]
    out_json = {"date": date, "rows": len(rows), "strategies": {}}
    for key in sorted(per):
        p = per[key]; n = len(p["rs"])
        mline = " ".join(f"{m}:{c}" for m, c in sorted(p["machines"].items()))
        lines.append(f"[{key}] ticks={n}  {mline}")
        lines.append(f"    R p50={_pct(p['rs'],.5):.3f} p90={_pct(p['rs'],.9):.3f} "
                     f"max={max(p['rs']) if p['rs'] else 0:.3f}  "
                     f"slope p90={_pct(p['slopes'],.9):.3f}/min  "
                     f"would_fire={p['would_fire']}  arm_episodes={len(p['arm_spans'])}")
        ps = pick_stats.get(key)
        if ps and ps["n"]:
            lines.append(f"    staged picks n={ps['n']}  target_delta p50="
                         f"{_pct(ps['deltas'],.5):.3f}  conv_ema p50={_pct(ps['convs'],.5):.3f}"
                         + (f"  spread%mid p50={_pct(ps['spreads'],.5):.4f}" if ps["spreads"] else ""))
        out_json["strategies"][key] = {
            "ticks": n, "machines": dict(p["machines"]),
            "r_p50": _pct(p["rs"], .5), "r_p90": _pct(p["rs"], .9),
            "would_fire": p["would_fire"], "arm_episodes": len(p["arm_spans"]),
            "staged_picks": (ps["n"] if ps else 0)}
    # ── v1.1: factor calibration ────────────────────────────────────────────
    lines.append("")
    lines.append("FACTOR CALIBRATION  (raw-input percentiles + ramped-output peg rates)")
    lines.append("  a ramped factor pegged on >%d%% of ticks is a constant, not evidence"
                 % int(PEG_ALARM * 100))
    fits = {}
    for key in sorted(per):
        fac = per[key]["factors"]
        if not fac:
            continue
        lines.append(f"  [{key}]")
        for fk in sorted(fac):
            vals = fac[fk]
            if not vals:
                continue
            if fk.endswith("_val"):
                hi = sum(1 for v in vals if v >= PEG_HI) / len(vals)
                lo = sum(1 for v in vals if v <= PEG_LO) / len(vals)
                flag = "  <-- PEGGED" if (hi > PEG_ALARM or lo > PEG_ALARM) else ""
                lines.append(f"    {fk:<14} n={len(vals):<6} hi={100*hi:3.0f}% "
                             f"lo={100*lo:3.0f}% graded={100*(1-hi-lo):3.0f}%{flag}")
            else:
                lines.append(f"    {fk:<14} n={len(vals):<6} p25={_pct(vals,.25):.3f} "
                             f"p50={_pct(vals,.5):.3f} p75={_pct(vals,.75):.3f} "
                             f"p95={_pct(vals,.95):.3f}")
                m = FACTOR_MAP.get(fk)
                if m and m[1]:
                    ramped, stem, inverted = m
                    rv = fac.get(ramped) or []
                    pegged = rv and (
                        sum(1 for v in rv if v >= PEG_HI) / len(rv) > PEG_ALARM or
                        sum(1 for v in rv if v <= PEG_LO) / len(rv) > PEG_ALARM)
                    if pegged:
                        fits[stem] = (round(_pct(vals, .25), 2), round(_pct(vals, .95), 2))
        out_json["strategies"].setdefault(key, {})["factors"] = {
            fk: {"n": len(v), "p25": _pct(v, .25), "p50": _pct(v, .5),
                 "p95": _pct(v, .95),
                 "peg_hi": (sum(1 for x in v if x >= PEG_HI) / len(v)) if v else 0.0,
                 "peg_lo": (sum(1 for x in v if x <= PEG_LO) / len(v)) if v else 0.0}
            for fk, v in fac.items() if v}
    if fits:
        lines.append("")
        lines.append("FIT SUGGESTIONS (p25 -> p95, ramp_calibration convention).")
        lines.append("  Trial on ONE box first, then fleet-wide — no redeploy needed:")
        for stem, (lo_v, hi_v) in sorted(fits.items()):
            lines.append(f"    export OT_TR_{stem}_LO={lo_v}  OT_TR_{stem}_HI={hi_v}")
        out_json["fit_suggestions"] = {k: {"lo": v[0], "hi": v[1]} for k, v in fits.items()}

    if anticipations:
        lines.append("")
        _lead = [a["lead_min"] for a in anticipations if a["lead_min"] is not None]
        _none = sum(1 for a in anticipations if a["kind"] == "no-prior-arm")
        lines.append("ANTICIPATION (did readiness ARM before the trade fired?)")
        lines.append(f"    fires {len(anticipations)}  with a prior arm "
                     f"{len(_lead)}  NO PRIOR ARM {_none}")
        if _lead:
            _s = sorted(_lead)
            lines.append(f"    lead time min: p50={_s[len(_s)//2]:.1f}  "
                         f"p90={_s[min(len(_s)-1, int(.9*len(_s)))]:.1f}  "
                         f"max={_s[-1]:.1f}")
        lines.append("    a NEGATIVE lead is impossible and means the pairing is "
                     "broken — it was, until v1.4")
        for a in anticipations[:40]:
            _l = "     n/a" if a["lead_min"] is None else f"{a['lead_min']:8.1f}m"
            lines.append(f"    {a['sym']:<6} {a['strategy']:<22} lead {_l}  "
                         f"[{a['kind']}] armed {a['armed_since']} -> fired {a['fired_at']}")
        if len(anticipations) > 40:
            lines.append(f"    … {len(anticipations) - 40} more (full list in the JSON)")
    out_json["anticipations"] = anticipations
    # v1.3 — COUNT THE SAME THING THE FIT SUGGESTIONS DO. This counted peg rates
    # on the RAW `_val` series while the fits (above) measure the RAMPED output,
    # so the headline and the list it points at could disagree — and the number
    # people read is the headline. The module's own premise is about the ramp:
    # "a corroborator pegged at its bound is a constant wearing new clothes."
    # A RAW value at its bound is frequently just what that factor is (a binary
    # corroborator is 0 or 1 by construction); a RAMPED output at its bound is
    # the term contributing nothing that varies, which is the actual alarm.
    # 2026-08-05 reported "9 pegged factor(s)" on the raw definition — the
    # ramped count is what the Aug 8-9 fits should be sized against.
    npeg = len(fits)
    headline = (f"🧭 readiness {date}: "
                + (f"{npeg} pegged ramp(s) — see FIT SUGGESTIONS; " if npeg else "")
                + (", ".join(f"{k} wf={per[k]['would_fire']} arm={len(per[k]['arm_spans'])}"
                             for k in sorted(per)) if per
                   else "no readiness rows yet (journal not harvested or fleet pre-v4.4)"))
    return lines, out_json, headline


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--journal-root", required=True)
    ap.add_argument("--reports-dir", required=True)
    ap.add_argument("--date", default=None, help="default: latest dated folder present")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    days = sorted(d for d in glob.glob(os.path.join(a.journal_root, "20*-*-*"))
                  if os.path.isdir(d))
    if a.date:
        day_dir = os.path.join(a.journal_root, a.date); date = a.date
    elif days:
        day_dir = days[-1]; date = os.path.basename(day_dir)
    else:
        print("🧭 readiness: no journal folders on disk yet")
        return 0                      # quiet night must never fail the chain
    lines, out_json, headline = digest(day_dir, date)
    os.makedirs(a.reports_dir, exist_ok=True)
    with open(os.path.join(a.reports_dir, f"readiness_digest_{date}.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")
    with open(os.path.join(a.reports_dir, f"readiness_digest_{date}.jsonl"), "w") as f:
        f.write(json.dumps(out_json) + "\n")
    print(headline if a.quiet else "\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
