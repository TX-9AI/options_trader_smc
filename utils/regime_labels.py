"""
utils/regime_labels.py — short display labels for regime names. v1.0

v1.0 — 2026-08-04 — NEW. One map, three consumers.

WHY THIS EXISTS AS A MODULE rather than a constant in whichever file needed it
first: three separate renderers independently abbreviated regime names by
truncating them — `regime_diary` at 4 characters, `replay_confluence` and
`regime_confluence`'s self-test at 5 — and ALL THREE collapsed TRENDING_BULL
and TRENDING_BEAR into one indistinguishable token ("TREN" / "TREND"). Sixteen
sessions of diary rows and every nightly emitted-distribution line printed the
same string for opposite regimes. Nothing errored; the reports simply could not
express the distinction, in a workstream where directional asymmetry is an open
question.

Fixing them one at a time would have left the next renderer free to invent a
fourth abbreviation, so the map lives in exactly one place and every consumer
imports it.

STDLIB ONLY, AND IT MUST STAY THAT WAY. `tests/regime_diary.py` is deliberately
dependency-free (it reads a tick log and nothing else) and runs on control from
the repo checkout; an import here that pulled in pandas would quietly change
what that tool needs to run.

The labels are the OPERATOR'S (2026-08-04): BULL and BEAR. An earlier cut of
mine used sign-suffixed abbreviations, which read as notation about the thing
rather than the thing itself; the superseded tokens are deliberately not spelled
anywhere in the tree, because the absence canary that pins them greps whole
files (see the changelog-prose trap in check_versions.sh).

Four characters each so columns stay aligned when a line is scanned rather than
parsed.
"""

REGIME_LABELS = {
    "TRENDING_BULL":     "BULL",
    "TRENDING_BEAR":     "BEAR",
    "RANGING":           "RANG",
    "BREAKOUT_VOLATILE": "BREA",
    "COMPRESSION":       "COMP",
    "SWEEP_REVERSAL":    "SWEE",
    "UNKNOWN":           "UNKN",
}


def label(name: str) -> str:
    """Short display label for a regime name.

    An unmapped name degrades to the old truncation rather than raising: a new
    regime must never be able to take down a nightly report, and a report that
    prints an odd token is fixable tomorrow. Every mapped name is unique, which
    `tests/test_regime_diary_render.py` asserts.
    """
    if not name:
        return "—"
    return REGIME_LABELS.get(name, str(name).split("_")[0][:4])
