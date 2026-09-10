"""Merge the per-job DSN Now archives into the single archive the pre-registered analysis reads.

    python experiments/dsn_now_probe/merge_archives.py --into D:/data/all D:/data/job1 D:/data/job2

The logging workflow uploads one archive per ~5.5-hour job; `analyze_feed_probe.py` reads one
directory. Merging is plumbing, and it must never become the place where evidence changes:

  * every referenced snapshot is re-hashed, and one whose bytes do not match its name is refused;
  * a digest seen in two jobs is the same bytes by construction and is stored once -- and the bytes
    are compared anyway, because "by construction" is a claim this repository checks;
  * index lines are copied verbatim, none dropped and none edited, in fetch-time order;
  * an index line naming a snapshot that is not there is refused, because the archive is incomplete;
  * the same line arriving twice is refused, because it almost certainly means one job's archive
    was passed twice and would otherwise be counted twice;
  * an existing destination is refused, so a merge is never quietly layered over an older one.

Snapshots present on disk but named by no index line are reported, not copied: they mean a job wrote
a snapshot and died before logging it, and that gap should be visible rather than repaired.

Exit status: 0 on success, 1 on any refusal. Standard library plus the repository's atomic writer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]


class MergeError(RuntimeError):
    """The inputs cannot be merged without altering or losing evidence."""


def merge(sources: list[pathlib.Path], into: pathlib.Path) -> dict[str, int]:
    sys.path.insert(0, str(REPO / "src"))
    from farsight.registry.atomic import write_atomic

    if into.exists():
        raise MergeError(f"{into} already exists; a merge is never layered over an older one")

    lines: list[tuple[str, str]] = []
    seen_lines: set[str] = set()
    stored: dict[str, bytes] = {}
    unreferenced = 0

    for source in sources:
        index = source / "index.jsonl"
        if not index.is_file():
            raise MergeError(f"{source} has no index.jsonl")
        referenced: set[str] = set()
        for raw in index.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            if raw in seen_lines:
                raise MergeError("the same index line appears twice (was one archive "
                                 f"passed twice?): {raw[:120]}")
            seen_lines.add(raw)
            entry = json.loads(raw)
            lines.append((entry["attempted_at_utc"], raw))
            digest = entry.get("sha256")
            if digest is None:
                continue                     # a failed attempt: kept as a line, has no snapshot
            referenced.add(digest)
            path = source / "snapshots" / digest[:2] / f"{digest}.xml"
            if not path.is_file():
                raise MergeError(f"{source}: index names snapshot {digest}, which is not there")
            body = path.read_bytes()
            if hashlib.sha256(body).hexdigest() != digest:
                raise MergeError(f"{source}: snapshot {digest} does not hash to its own name")
            if digest in stored and stored[digest] != body:
                raise MergeError(f"two different byte strings claim digest {digest}")
            stored[digest] = body
        on_disk = {p.stem for p in (source / "snapshots").rglob("*.xml")} if (
            source / "snapshots").is_dir() else set()
        unreferenced += len(on_disk - referenced)

    for digest, body in stored.items():
        write_atomic(into / "snapshots" / digest[:2] / f"{digest}.xml", body)
    ordered = "".join(raw + "\n" for _when, raw in sorted(lines))
    write_atomic(into / "index.jsonl", ordered.encode("utf-8"))
    return {"sources": len(sources), "index_lines": len(lines), "snapshots": len(stored),
            "unreferenced_snapshots": unreferenced}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--into", required=True, type=pathlib.Path,
                        help="destination; must not already exist")
    parser.add_argument("sources", nargs="+", type=pathlib.Path, help="per-job archive directories")
    args = parser.parse_args(argv)
    try:
        summary = merge([s.expanduser() for s in args.sources], args.into.expanduser())
    except MergeError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    for key, value in summary.items():
        print(f"{key}: {value}")
    if summary["unreferenced_snapshots"]:
        print("note: some snapshots are named by no index line -- a job likely stopped between "
              "writing a snapshot and logging it. Not copied; the gap stays visible.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
