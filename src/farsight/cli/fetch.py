"""``farsight fetch`` — the only verb that reaches the network.

ADR-012 decision 1 fixes the spelling:
``farsight fetch kernel --url <url> --expect-sha256 <hex> --into <cache>``. ADR-024 gives the
failure exit code 30, ``acquisition_failure``: "bytes did not match ``--expect-sha256``, or
transport failed."

This module is the **only** importer of ``farsight.acquire``, which is the only package permitted
a networking library. That chain is what makes "the runner and the verifier make zero network
calls, ever" a structural property rather than a promise.

``--expect-sha256`` is required, with no flag to skip it. A fetch without a declared digest would
record whatever arrived, which is a log line rather than a check.
"""

from __future__ import annotations

import json as _json
from pathlib import Path
from typing import Annotated

import typer

from farsight.cli import exit_codes

__all__ = ["app"]

app = typer.Typer(name="fetch", help="Fetch an external artifact into the local cache.")


@app.command("kernel")
def fetch_kernel_command(
    ctx: typer.Context,
    url: Annotated[str, typer.Option("--url", help="Source URL (https).")],
    expect_sha256: Annotated[
        str | None,
        typer.Option("--expect-sha256",
                     help="FarSight's content address for these bytes, when it is already known."),
    ] = None,
    expect_md5: Annotated[
        str | None,
        typer.Option("--expect-md5",
                     help="The MD5 the PUBLISHER stated, e.g. from a PDS4 bundle's checksum.tab. "
                          "Verifies a first acquisition, which --expect-sha256 cannot."),
    ] = None,
    into: Annotated[
        Path | None, typer.Option("--into", help="Cache root. Defaults to $FARSIGHT_HOME/kernels.")
    ] = None,
    license_note: Annotated[
        str,
        typer.Option("--license-note",
                     help="Redistribution terms, recorded with the artifact."),
    ] = "",
) -> None:
    """Fetch a kernel, verify it against a declared digest, and cache it.

    At least one of --expect-sha256 and --expect-md5 is required, and both are checked when both
    are given. Neither has a default and there is no flag to skip verification: ADR-012 makes the
    digest a precondition, so that a fetch is a CHECK on what arrived rather than a description
    of it.
    """
    # Imported here rather than at module scope so that `farsight --help` does not construct the
    # acquisition path at all. The network stays behind the verb that needs it.
    from farsight.acquire.fetch import AcquisitionError, fetch_kernel
    from farsight.registry.kernel_cache import KernelCache
    from farsight.registry.paths import kernel_cache_root

    options = ctx.obj or {}
    cache_root = into if into is not None else kernel_cache_root(options.get("home"))
    cache = KernelCache(cache_root)

    try:
        artifact, path = fetch_kernel(
            url, expect_sha256, cache, license_note=license_note, expect_md5=expect_md5
        )
    except AcquisitionError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(exit_codes.ACQUISITION_FAILURE) from exc

    if options.get("json"):
        typer.echo(_json.dumps({"artifact": artifact.model_dump(mode="json"), "path": str(path)},
                               indent=2, sort_keys=True))
    elif not options.get("quiet"):
        typer.echo(f"{artifact.sha256}  {artifact.size_bytes} bytes  -> {path}")
