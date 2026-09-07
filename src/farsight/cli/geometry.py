"""``farsight geometry`` -- the weeks 1-2 exit gate. ADR-024.

A **leaf** command, not a group: ``farsight geometry --design PATH --out DIR``. ADR-024 keeps the
plan's literal spelling because it is the wording of the gate, and states the reason the verb
exists at all -- weeks 1-2 have no planner, no ledger and no package builder, and the geometry
service must still be exercisable and hash-stable.

**It writes the `run` audit action, not a `geometry` one.** ADR-012's action enumeration is closed
and ``run`` is the only admissible member; ``detail_json`` carries the design path, which is what
tells an auditor reading the chain that this was a week-1 geometry probe rather than a campaign.

**What it does not do.** It does not build an evidence package, does not compute metrics, does not
evaluate claims, and its output directory is not a package. The gate it serves is narrower than it
sounds: geometry that is hash-stable, which means running it twice produces identical channel
hashes.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Annotated

import typer

from farsight.cli import exit_codes
from farsight.schemas.errors import FarSightError

__all__ = ["geometry_command"]


def _exit_code_for(exc: FarSightError) -> int:
    """Map a failure to ADR-024's registry. Explicit, because the distinctions are the point.

    An operator whose `spice` extra is missing and an operator whose design is unhonorable get
    different codes because they have completely different fixes -- and the registry says so:
    `environment_refusal` names "a required engine extra is not installed" while
    `precondition_refusal` names "an unhonorable RunSpec".
    """
    from farsight.cli.run_geometry import GeometryDesignError
    from farsight.registry.kernel_cache import KernelCacheError
    from farsight.schemas.errors import MissingEngineExtra

    if isinstance(exc, MissingEngineExtra):
        return exit_codes.ENVIRONMENT_REFUSAL
    if isinstance(exc, KernelCacheError):
        # A cache file whose bytes do not hash to its own path name is the AT-3 tamper class.
        return exit_codes.INTEGRITY_FAILURE
    if isinstance(exc, GeometryDesignError):
        return exit_codes.SCHEMA_FAILURE
    return exit_codes.PRECONDITION_REFUSAL


def _emit(payload: dict, *, as_json: bool, quiet: bool) -> None:
    if quiet:
        return
    if as_json:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    for key, value in payload.items():
        if isinstance(value, list):
            typer.echo(f"{key}:")
            for item in value:
                typer.echo(f"  {item}")
        else:
            typer.echo(f"{key}: {value}")


def geometry_command(
    ctx: typer.Context,
    design: Annotated[Path, typer.Option("--design", help="Path to a GeometryDesign JSON file.")],
    out: Annotated[Path, typer.Option("--out", help="Output directory for channels.")],
    home: Annotated[
        Path | None, typer.Option("--home", help="FarSight home. Defaults to $FARSIGHT_HOME.")
    ] = None,
    shadow_units: Annotated[
        bool,
        typer.Option(
            "--shadow-units",
            help="Debug: re-check dimensions and cross-check epochs against astropy. "
                 "Never for a run offered to an evidence package (ADR-008).",
        ),
    ] = False,
) -> None:
    """Compute hash-stable geometry from a frozen geometry design."""
    parent = ctx.obj or {}
    as_json = bool(parent.get("json"))
    quiet = bool(parent.get("quiet"))

    # Imported inside the command so that `farsight --help` and every other verb still work on an
    # install without the `spice` extra. ADR-007 makes the auditor's zero-extras install the
    # scarcest resource in the architecture; a module-level import here would spend it.
    from farsight.cli.run_geometry import run_geometry

    try:
        result = run_geometry(
            design_path=design,
            out_dir=out,
            home=home,
            shadow_units=shadow_units,
            ts_utc=_dt.datetime.now(_dt.UTC).isoformat(timespec="seconds"),
        )
    except FarSightError as exc:
        code = _exit_code_for(exc)
        typer.echo(f"error: {exc}", err=True)
        typer.echo(f"exit {code}: {exit_codes.meaning(code)}", err=True)
        raise typer.Exit(code) from exc

    _emit(result, as_json=as_json, quiet=quiet)
    raise typer.Exit(exit_codes.OK)
