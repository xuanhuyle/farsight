"""Archive snapshots of NASA's public DSN Now feed, for the first project's week-1 go/no-go.

    python scripts/log_dsn_now.py --into D:/farsight-data/dsn_now --once
    python scripts/log_dsn_now.py --into D:/farsight-data/dsn_now --every 300 --hours 168

WHAT THIS IS FOR. The first-project plan uses the feed's per-spacecraft `power` attribute as a
*possible* answer key for predicted received power. Whether that attribute is a physical
measurement is UNKNOWN. The feed states no unit, no definition and no calibration, and a first
look showed integer values, clustering on multiples of ten, and sentinels such as -480 on inactive
signals. This script does not decide the question. It archives what the feed said, byte for byte,
so the decision can be made -- and re-made by anyone -- offline against a fixed record.

WHAT IT RECORDS, IN TWO PLACES:

    snapshots/<first2>/<sha256>.xml   the exact bytes served, named by their own digest
    index.jsonl                       one line per ATTEMPT, failed attempts included

Failed attempts are logged, never skipped. A gap must be distinguishable from "the DSN was not
tracking that spacecraft", or the analysis would read a network outage as a tracking pattern --
the silent-no-op shape this repository has now removed four times. Identical consecutive snapshots
share one file (same digest), but every attempt keeps its own index line and fetch time: the feed
repeating itself is a fact worth keeping too.

NO DEFAULT LOCATION. ADR-012 decision 4 keeps mission data under operator-declared data roots,
not under `$FARSIGHT_HOME`, and no data-root mechanism exists yet, so the caller names the
directory. These snapshots are referent data, not FarSight state.

A network script outside the truth loop, on the same footing as `fetch_horizons_golden.py`:
nothing under `src/` imports it and nothing in the test suite reaches the network. The interval
floor is 60 s; the public page refreshes every few seconds, so this is a small fraction of one
viewer's load.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable

REPO = pathlib.Path(__file__).resolve().parents[1]
FEED = "https://eyes.nasa.gov/dsn/data/dsn.xml"
USER_AGENT = "farsight-dsn-now-probe/0.0.1 (research archive; one request per interval)"
MINIMUM_INTERVAL_S = 60


def _atomic_writer() -> Callable[[pathlib.Path, bytes], pathlib.Path]:
    """The repository's one sanctioned atomic writer, rather than a second implementation."""
    sys.path.insert(0, str(REPO / "src"))
    from farsight.registry.atomic import write_atomic

    return write_atomic


def fetch_once(
    into: pathlib.Path, write_atomic: Callable[[pathlib.Path, bytes], pathlib.Path]
) -> dict[str, object]:
    """One attempt. Returns the index entry; a `sha256` key means a snapshot was archived."""
    entry: dict[str, object] = {
        "attempted_at_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "url": FEED,
    }
    try:
        request = urllib.request.Request(FEED, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=60) as response:  # https, fixed host
            body = response.read()
            entry["http_status"] = response.status
    except OSError as exc:  # URLError and TimeoutError are both OSError
        entry["error"] = f"{type(exc).__name__}: {exc}"
        return entry

    # A body that is not the feed must never be archived as a snapshot of it: an HTML error page
    # served with status 200 would otherwise enter the record looking like a quiet DSN.
    entry["bytes"] = len(body)
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        entry["error"] = f"not XML: {exc}"
        return entry
    if root.tag != "dsn":
        entry["error"] = f"root element is <{root.tag}>, not <dsn>"
        return entry

    digest = hashlib.sha256(body).hexdigest()
    path = into / "snapshots" / digest[:2] / f"{digest}.xml"
    if not path.exists():
        write_atomic(path, body)

    stamp = (root.findtext("timestamp") or "").strip()
    entry["sha256"] = digest
    entry["feed_timestamp_ms"] = int(stamp) if stamp.isdigit() else None
    entry["active_data_downlinks"] = sum(
        1
        for signal in root.iter("downSignal")
        if signal.get("active") == "true" and signal.get("signalType") == "data"
    )
    return entry


def append_index(into: pathlib.Path, entry: dict[str, object]) -> None:
    """Append one line, fsynced, in binary mode.

    Binary so Windows does not translate the newline; fsynced so a line either lands whole or is
    absent after a crash. An append-only log is not a replace, so `write_atomic` is not the tool.
    """
    into.mkdir(parents=True, exist_ok=True)
    line = (json.dumps(entry, sort_keys=True) + "\n").encode("utf-8")
    with open(into / "index.jsonl", "ab") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())


def _report(entry: dict[str, object]) -> None:
    if "sha256" in entry:
        print(f"{entry['attempted_at_utc']}  ok   {str(entry['sha256'])[:12]}  "
              f"{entry['bytes']} B  active data downlinks: {entry['active_data_downlinks']}")
    else:
        print(f"{entry['attempted_at_utc']}  FAIL {entry.get('error')}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Archive DSN Now feed snapshots.")
    parser.add_argument("--into", required=True, type=pathlib.Path,
                        help="archive directory; deliberately has no default (ADR-012 decision 4)")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true", help="take a single snapshot")
    mode.add_argument("--every", type=int, metavar="SECONDS", help="interval between attempts")
    parser.add_argument("--hours", type=float, help="how long to run with --every")
    args = parser.parse_args(argv)

    if args.every is not None:
        if args.every < MINIMUM_INTERVAL_S:
            parser.error(f"--every must be at least {MINIMUM_INTERVAL_S} s")
        if args.hours is None or args.hours <= 0:
            parser.error("--every needs --hours greater than zero; an unbounded logger is refused")

    write_atomic = _atomic_writer()
    into = args.into.expanduser()

    if args.once:
        entry = fetch_once(into, write_atomic)
        append_index(into, entry)
        _report(entry)
        return 0 if "sha256" in entry else 1

    deadline = time.monotonic() + args.hours * 3600
    archived = failed = 0
    while True:
        started = time.monotonic()
        entry = fetch_once(into, write_atomic)
        append_index(into, entry)
        _report(entry)
        if "sha256" in entry:
            archived += 1
        else:
            failed += 1
        if time.monotonic() + args.every > deadline:
            break
        time.sleep(max(0.0, args.every - (time.monotonic() - started)))

    print(f"finished: {archived} snapshots archived, {failed} failed attempts")
    # A run in which every attempt failed produced no evidence, and must not exit as a success.
    return 0 if archived else 1


if __name__ == "__main__":
    raise SystemExit(main())
