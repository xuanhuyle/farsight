"""Decide the DSN Now feed probe exactly as PREREGISTRATION.md fixes it.

    python experiments/dsn_now_probe/analyze_feed_probe.py --archive D:/data/dsn_now
    python experiments/dsn_now_probe/analyze_feed_probe.py --archive D:/data/dsn_now --extended

Reads only what `scripts/log_dsn_now.py` archived: `index.jsonl` and the digest-named snapshots.
Every threshold, antenna set and selection rule here is copied from PREREGISTRATION.md, which was
committed before the logging run began. If the two ever disagree, the pre-registration governs and
the disagreement is a defect in this file.

Each snapshot is re-hashed on load and must match its file name and index entry. An analysis that
silently read a corrupted or substituted snapshot would decide a plan branch on bytes nobody
fetched.

Exit status: 0 PASS, 1 FAIL, 3 INCONCLUSIVE. (2 is argparse's usage error.)
Standard library only.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import pathlib
import statistics
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass

# --- copied from PREREGISTRATION.md -----------------------------------------------------------
ANTENNAS_70M = frozenset({"DSS14", "DSS43", "DSS63"})
ANTENNAS_34M_BWG = frozenset({"DSS25", "DSS26", "DSS34", "DSS35", "DSS36", "DSS54", "DSS55"})
MIN_ELEVATION_DEG = 20.0
MIN_SNAPSHOTS_PER_DISH_DATE = 3
BAND_DB = (3.3, 9.0)
MIN_PAIRINGS = 3
MIN_DATES = 2
PASS_FRACTION = 0.80
WINDOW_DAYS = 7
EXTENDED_WINDOW_DAYS = 14
SENTINEL_AT_OR_BELOW = -300.0
# ------------------------------------------------------------------------------------------------

PASS, FAIL, INCONCLUSIVE = 0, 1, 3


class ArchiveError(RuntimeError):
    """The archive cannot be trusted as the record of what the feed said."""


@dataclass(frozen=True)
class Sample:
    feed_ms: int
    date: str
    dish: str
    elevation: float | None
    is_array: bool
    is_mspa: bool
    spacecraft: str
    band: str
    active: bool
    signal_type: str
    power: float | None


def _number(text: str | None) -> float | None:
    try:
        value = float(text) if text is not None else None
    except ValueError:
        return None
    return value if value is not None and math.isfinite(value) else None


def load(archive: pathlib.Path, window_days: int) -> tuple[list[Sample], dict[str, object]]:
    entries = [json.loads(line) for line in
               (archive / "index.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    archived = [e for e in entries if "sha256" in e]
    info: dict[str, object] = {"attempts": len(entries),
                               "failed_attempts": len(entries) - len(archived)}
    if not archived:
        info["distinct_feed_timestamps"] = 0
        return [], info

    first = min(dt.datetime.fromisoformat(e["attempted_at_utc"]) for e in archived)
    end = first + dt.timedelta(days=window_days)
    info["window"] = f"{first.isoformat()} .. {end.isoformat()} ({window_days} days)"

    seen: set[int] = set()
    samples: list[Sample] = []
    for entry in sorted(archived, key=lambda e: e["attempted_at_utc"]):
        when = dt.datetime.fromisoformat(entry["attempted_at_utc"])
        if not first <= when < end:
            continue
        stamp = entry.get("feed_timestamp_ms")
        key = int(stamp) if stamp is not None else int(when.timestamp() * 1000)
        if key in seen:
            continue
        seen.add(key)

        digest = entry["sha256"]
        body = (archive / "snapshots" / digest[:2] / f"{digest}.xml").read_bytes()
        if hashlib.sha256(body).hexdigest() != digest:
            raise ArchiveError(f"snapshot {digest} does not hash to its own name")
        root = ET.fromstring(body)
        date = dt.datetime.fromtimestamp(key / 1000, dt.UTC).date().isoformat()
        for dish in root.iter("dish"):
            for signal in dish.findall("downSignal"):
                samples.append(Sample(
                    feed_ms=key, date=date, dish=dish.get("name", ""),
                    elevation=_number(dish.get("elevationAngle")),
                    is_array=dish.get("isArray") == "true", is_mspa=dish.get("isMSPA") == "true",
                    spacecraft=signal.get("spacecraft", ""), band=signal.get("band", ""),
                    active=signal.get("active") == "true",
                    signal_type=signal.get("signalType", ""), power=_number(signal.get("power")),
                ))
    info["distinct_feed_timestamps"] = len(seen)
    return samples, info


def eligible(s: Sample) -> bool:
    return (s.active and s.signal_type == "data" and s.band == "X" and not s.is_array
            and not s.is_mspa and s.power is not None and s.elevation is not None
            and s.elevation >= MIN_ELEVATION_DEG)


def antenna_class(dish: str) -> str | None:
    if dish in ANTENNAS_70M:
        return "70m"
    if dish in ANTENNAS_34M_BWG:
        return "34m"
    return None


def pairings(samples: list[Sample]) -> list[dict[str, object]]:
    powers: dict[tuple[str, str, str, str], list[float]] = defaultdict(list)
    for s in samples:
        cls = antenna_class(s.dish)
        if eligible(s) and cls is not None:
            powers[(s.spacecraft, s.date, cls, s.dish)].append(s.power)  # type: ignore[arg-type]

    def pick(spacecraft: str, date: str, cls: str) -> tuple[str, list[float]] | None:
        candidates = [(dish, values) for (sc, d, c, dish), values in powers.items()
                      if (sc, d, c) == (spacecraft, date, cls)
                      and len(values) >= MIN_SNAPSHOTS_PER_DISH_DATE]
        if not candidates:
            return None
        return min(candidates, key=lambda t: (-len(t[1]), int(t[0][3:])))

    result = []
    for spacecraft, date in sorted({(sc, d) for sc, d, _c, _dish in powers}):
        big, small = pick(spacecraft, date, "70m"), pick(spacecraft, date, "34m")
        if big is None or small is None:
            continue
        difference = statistics.median(big[1]) - statistics.median(small[1])
        result.append({
            "spacecraft": spacecraft, "date": date,
            "dish_70m": big[0], "n_70m": len(big[1]), "median_70m": statistics.median(big[1]),
            "dish_34m": small[0], "n_34m": len(small[1]), "median_34m": statistics.median(small[1]),
            "difference_db": difference,
            "in_band": BAND_DB[0] <= difference <= BAND_DB[1],
        })
    return result


def decide(pairs: list[dict[str, object]]) -> tuple[int, str]:
    n = len(pairs)
    dates = {p["date"] for p in pairs}
    if n < MIN_PAIRINGS or len(dates) < MIN_DATES:
        return INCONCLUSIVE, (f"INCONCLUSIVE: {n} pairing(s) on {len(dates)} date(s); "
                              f"need {MIN_PAIRINGS} on {MIN_DATES}")
    needed = math.ceil(PASS_FRACTION * n)
    inside = sum(bool(p["in_band"]) for p in pairs)
    verdict = PASS if inside >= needed else FAIL
    word = "PASS" if verdict == PASS else "FAIL"
    return verdict, (f"{word}: {inside} of {n} pairings inside {list(BAND_DB)} dB "
                     f"(needed {needed}), across {len(dates)} dates")


def _ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def describe(samples: list[Sample]) -> None:
    usable = [s.power for s in samples if eligible(s)]
    if usable:
        integers = sum(float(v).is_integer() for v in usable)
        tens = sum(float(v).is_integer() and int(v) % 10 == 0 for v in usable)
        print(f"  eligible values: {len(usable)}; integers {integers / len(usable):.0%}; "
              f"on multiples of 10 {tens / len(usable):.0%}")
    else:
        print("  eligible values: none")
    for active in (True, False):
        group = [s for s in samples if s.active == active and s.power is not None]
        sentinels = sum(s.power <= SENTINEL_AT_OR_BELOW for s in group)  # type: ignore[operator]
        print(f"  active={active!s:5}: {len(group)} signals with a number, {sentinels} sentinels "
              f"(<= {SENTINEL_AT_OR_BELOW:.0f})")

    passes: dict[tuple[str, str, str], list[Sample]] = defaultdict(list)
    for s in samples:
        if (s.active and s.signal_type == "data" and s.band == "X" and not s.is_array
                and s.power is not None and s.elevation is not None):
            passes[(s.spacecraft, s.dish, s.date)].append(s)
    rhos = []
    for group in passes.values():
        elevations = [s.elevation for s in group]
        levels = [s.power for s in group]
        if len(group) >= 5 and len(set(elevations)) > 1 and len(set(levels)) > 1:
            rhos.append(statistics.correlation(_ranks(elevations), _ranks(levels)))  # type: ignore[arg-type]
    if rhos:
        print(f"  elevation vs power: {len(rhos)} passes with variation, median Spearman "
              f"{statistics.median(rhos):+.2f}")
    else:
        print("  elevation vs power: no pass had both elevation and power vary")

    both: dict[tuple[str, str], dict[bool, list[float]]] = defaultdict(lambda: defaultdict(list))
    for s in samples:
        if s.active and s.signal_type == "data" and s.band == "X" and s.power is not None:
            both[(s.spacecraft, s.date)][s.is_array].append(s.power)
    diffs = [statistics.median(v[True]) - statistics.median(v[False])
             for v in both.values() if v[True] and v[False]]
    print(f"  arrayed minus single-dish median power: "
          f"{[round(d, 1) for d in diffs] if diffs else 'no spacecraft-date had both'}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--archive", required=True, type=pathlib.Path)
    parser.add_argument("--extended", action="store_true",
                        help=f"the single pre-registered extension to {EXTENDED_WINDOW_DAYS} days")
    args = parser.parse_args(argv)

    window = EXTENDED_WINDOW_DAYS if args.extended else WINDOW_DAYS
    samples, info = load(args.archive.expanduser(), window)
    print("DSN Now feed probe -- decided under PREREGISTRATION.md")
    for key, value in info.items():
        print(f"  {key}: {value}")

    pairs = pairings(samples)
    print(f"\nPairings (70 m minus 34 m BWG, same spacecraft, X-band, same UTC date): {len(pairs)}")
    for p in pairs:
        print(f"  {p['date']} {p['spacecraft']:6s} {p['dish_70m']}({p['n_70m']}) "
              f"{p['median_70m']:7.1f}  {p['dish_34m']}({p['n_34m']}) {p['median_34m']:7.1f}  "
              f"diff {p['difference_db']:+5.1f} dB  {'inside' if p['in_band'] else 'OUTSIDE'}")

    print("\nReported, not gating:")
    describe(samples)

    verdict, sentence = decide(pairs)
    print(f"\n{sentence}")
    if verdict == INCONCLUSIVE and not args.extended:
        print("Pre-registered next step: rerun with --extended once the archive spans 14 days.")
    elif verdict == INCONCLUSIVE:
        print("Pre-registered consequence: treated as FAIL for the plan -> candidate B.")
    return verdict


if __name__ == "__main__":
    raise SystemExit(main())
