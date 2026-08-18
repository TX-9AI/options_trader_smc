"""shadow/trading_day.py v1.0 — standalone US-market trading-day check.

Self-contained (stdlib only, no shadow/* imports) so it can run as a plain
script from a systemd ExecCondition. Exits 0 on a trading day, 1 on a
weekend or US market holiday — the start service uses that to SKIP (not fail)
on holidays. Evaluates the date in ET regardless of the box's system timezone.

⚠ Holiday list is hardcoded and must be refreshed annually (2026–2027 below).
Fail-safe: a wrong 'holiday' just means shadow doesn't observe that day (no harm);
a missed holiday means it observes an empty tape (harmless noise), never a trade.
"""
import datetime
import sys
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# NYSE full-day closes (observed dates). Refresh each year.
US_MARKET_HOLIDAYS = {
    # 2026
    "2026-01-01",  # New Year's Day
    "2026-01-19",  # MLK Jr. Day
    "2026-02-16",  # Presidents' Day
    "2026-04-03",  # Good Friday
    "2026-05-25",  # Memorial Day
    "2026-06-19",  # Juneteenth
    "2026-07-03",  # Independence Day (observed; Jul 4 is Sat)
    "2026-09-07",  # Labor Day
    "2026-11-26",  # Thanksgiving
    "2026-12-25",  # Christmas
    # 2027
    "2027-01-01",  # New Year's Day
    "2027-01-18",  # MLK Jr. Day
    "2027-02-15",  # Presidents' Day
    "2027-03-26",  # Good Friday
    "2027-05-31",  # Memorial Day
    "2027-06-18",  # Juneteenth (observed; Jun 19 is Sat)
    "2027-07-05",  # Independence Day (observed; Jul 4 is Sun)
    "2027-09-06",  # Labor Day
    "2027-11-25",  # Thanksgiving
    "2027-12-24",  # Christmas (observed; Dec 25 is Sat)
}


def is_trading_day(d: datetime.date | None = None) -> bool:
    if d is None:
        d = datetime.datetime.now(ET).date()
    if d.weekday() >= 5:          # Sat/Sun
        return False
    return d.isoformat() not in US_MARKET_HOLIDAYS


if __name__ == "__main__":
    sys.exit(0 if is_trading_day() else 1)
