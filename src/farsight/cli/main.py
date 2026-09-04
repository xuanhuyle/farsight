"""The FarSight command line. ADR-024.

The CLI is the whole user interface -- there is no web UI, in the MVP or in the roadmap -- and
its surface is unusually load-bearing for a command line. ``report/summary.md`` is generated from
package JSON and carries the audit instructions, so **command names and exit codes are printed
into shipped evidence packages**. Renaming a verb after packages ship makes the instructions in
those packages wrong forever, and a package whose own instructions do not work is worse than a
package with none: it is the first thing an auditor tries and the first impression they form.

**Verbs appear here when they work.** This module currently declares the global options and
``--version`` and nothing else. That is deliberate: a stub verb that accepts its arguments and
does nothing is indistinguishable, from a script's point of view, from one that succeeded. The
same reasoning made ``enumerate_outer`` refuse a sampling plan it could not honour rather than
silently return two vertices. Verbs land with their implementations, and until then the command
does not exist rather than existing and lying.

The global options are ADR-024's, and are accepted on every command: ``--json``, ``--quiet``,
``--home PATH``, ``--no-color``, ``--version``.
"""

from __future__ import annotations

import json as _json
from pathlib import Path
from typing import Annotated, Optional

import typer

from farsight.cli import exit_codes

__all__ = ["app", "main"]

app = typer.Typer(
    name="farsight",
    help=(
        "Deep-space autonomy verification and mission evidence. "
        "Exit codes are a contract (ADR-024): run `farsight --exit-codes` for the registry."
    ),
    no_args_is_help=True,
    add_completion=False,
)


def _version() -> str:
    """The installed distribution version, or a marker when running from a source tree."""
    from importlib.metadata import PackageNotFoundError, version  # noqa: PLC0415

    try:
        return version("farsight")
    except PackageNotFoundError:  # running from a checkout with no install
        return "0+unknown"


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: Annotated[
        bool, typer.Option("--version", help="Print the version and exit.")
    ] = False,
    exit_codes_flag: Annotated[
        bool,
        typer.Option(
            "--exit-codes",
            help="Print the exit-code registry and exit. The registry is append-only.",
        ),
    ] = False,
    as_json: Annotated[
        bool, typer.Option("--json", help="Emit machine-readable output.")
    ] = False,
    quiet: Annotated[bool, typer.Option("--quiet", help="Suppress progress output.")] = False,
    home: Annotated[
        Optional[Path], typer.Option("--home", help="FarSight home directory.")
    ] = None,
    no_color: Annotated[bool, typer.Option("--no-color", help="Disable colour.")] = False,
) -> None:
    """Global options, accepted on every command (ADR-024)."""
    ctx.obj = {"json": as_json, "quiet": quiet, "home": home, "no_color": no_color}

    if version:
        typer.echo(_json.dumps({"version": _version()}) if as_json else _version())
        raise typer.Exit(exit_codes.OK)

    if exit_codes_flag:
        if as_json:
            typer.echo(
                _json.dumps(
                    [{"code": e.code, "symbol": e.symbol, "meaning": e.meaning}
                     for e in exit_codes.REGISTRY],
                    indent=2,
                )
            )
        else:
            for entry in exit_codes.REGISTRY:
                typer.echo(f"{entry.code:>3}  {entry.symbol:<24}  {entry.meaning}")
        raise typer.Exit(exit_codes.OK)
