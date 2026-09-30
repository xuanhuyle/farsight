# FarSight

A verification and mission-evidence platform for autonomous deep-space spacecraft.

FarSight is **not** another spacecraft simulator. SPICE, Basilisk, GMAT and Tudat already do
the physics well, and FarSight orchestrates them rather than competing with them. What it adds
is the part nobody else provides together: model provenance, cross-engine validation, an honest
separation between the uncertainty you can put a distribution on and the uncertainty you
cannot, fault injection with common-cause structure, and reproducible evidence packages that a
stranger can verify without installing any simulation engine at all.

The question it exists to answer is not "what is the probability this mission succeeds". It is:

> Which assumptions decide whether this architecture works, how much does each one matter, at
> what value does it break, and what measurement would reduce that uncertainty most?

## Status

**Early, and now doing work.** The architecture is settled, the core is running, and it has been
pointed at real published analyses.

- 31 accepted architecture decision records in [`docs/adr/`](docs/adr/README.md)
- The approved 8-week plan in [`FARSIGHT_FOUNDATION_PLAN.md`](FARSIGHT_FOUNDATION_PLAN.md)
- Running: canonical identity, the uncertainty type system, SPICE geometry cross-checked against
  JPL Horizons, a verified kernel cache, reproducible container runs, and a CLI
- Not yet: fault injection, cross-engine comparison, published evidence packages

### What has been checked so far

Three published analyses have been rebuilt from the inputs their own documents print, each against
a standard fixed before the answer was known. **[`FINDINGS.md`](FINDINGS.md)** is the readable
account: what rebuilt, what did not, and what the sources never wrote down.

The short version — a JPL link budget whose tables do not share one aggregation convention; a NASA
public data feed that failed a pre-registered test to serve as an answer key; and a well-cited
Pioneer anomaly paper whose numbers mostly rebuild exactly, with two that do not and an input that
turns out to be recoverable from geometry the paper never connects to it.

All of it is internally cross-checked and **not externally expert-reviewed**
([ADR-030](docs/adr/)).

### One runnable example: an evidence package

The Pioneer reproduction is the first experiment wired through the evidence machinery. Build a
package, then verify it offline:

```bash
python experiments/pioneer_thermal/build_evidence_package.py --out /tmp/pioneer_pkg
python experiments/pioneer_thermal/verify_evidence_package.py /tmp/pioneer_pkg
```

Verification makes four separate checks — file integrity, schema and reference consistency,
numerical recomputation from the packaged inputs, and agreement with the pre-registered targets
— and says which one failed. It runs on the base install with **no engine extras and no network
access**, and it leaves the package byte-identical.

**What a verified package establishes:** the files are the ones that were sealed, every document
satisfies its schema, every reference resolves inside the package, and recomputing from the
packaged inputs reproduces the packaged results. **What it does not:** that the physics is
right, that the reproduction succeeded, or that anyone external has reviewed it. This particular
reproduction misses two of its pre-registered gates, and its package verifies cleanly while
saying so — packaging a failed result is a requirement, not an accident.

The format is a labelled subset of [ADR-007](docs/adr/ADR-007-evidence-package-format.md); every
package carries a `PARTIAL_FORMAT.md` naming precisely what is unsupported. `farsight evidence`
CLI verbs, `replay`, run channels and shipped JSON Schemas are **not** implemented.

## The ideas that shape everything else

**Unknown is a valid state.** Uncertainty is a five-member type: a value you know, a
distribution you can defend, an interval you believe, a set of alternatives you cannot rank,
and an outright unknown. The API is deliberately asymmetric — the samplable kinds expose
`sample()`, the epistemic kinds expose only `enumerate_outer()`, and `Unknown` exposes neither.
There is no method named `to_distribution` anywhere in this codebase, and
[tests assert its absence](tests/unit/test_belief.py). Turning ignorance into a probability is a
judgement a human signs, not something a sampler does at 3 a.m. inside a ten-thousand-run
campaign.

**Physics belongs to models.** FarSight owns the run protocol and the evidence format; it never
owns a spacecraft ontology. There is no `Spacecraft` type, no `Population` type, no network
domain. A topology node is a name with children and no values, and FarSight never dispatches on
what you called it. This is the discipline that keeps the project from becoming the
cross-simulator meta-framework that every predecessor died of.

**Identity is content, not a database row.** Every frozen object is SHA-256 over RFC 8785
canonical JSON. No floating-point number appears in a hashed document, ever — physical
quantities are decimal strings plus a unit, which removes the least portable part of canonical
JSON from the trust surface and keeps `"0.220"` distinguishable from `"0.22"`, because
significant figures are an engineering claim.

**Refusal over silent approximation.** When a fault cannot be honestly lowered onto an engine,
when a design states a quantity twice and disagrees with itself, when a model reference does not
resolve — FarSight refuses at freeze and names the thing, rather than approximating and
continuing.

**Rules are prevented, not policed.** Every ADR names the mechanical check that makes violating
it fail, and the week that check first goes green. Where mechanization is genuinely impossible,
the record says so in those words and names the review item that substitutes.

## Install

```bash
pip install -e ".[dev]"
```

Python 3.12 (the ceiling of the GMAT and Basilisk supported ranges). Simulation engines are
optional extras — `spice`, `basilisk`, `gmat` — and deliberately not core dependencies, because
verifying an evidence package must work on a clean install with no compiled engine present.

## Test

```bash
pytest tests/unit -q
```

```bash
lint-imports
```

The second command is not a formality. Boundary erosion is how a modular monolith dies, so the
package boundaries are executable contracts from the first commit — including the one that
matters commercially: `evidence/` and `hashing/` may never import `engines/`.

## Layout

```
src/farsight/
  schemas/     the only typed vocabulary; imports nothing else in FarSight
  hashing/     canonical JSON and content addressing
  units/       validate and normalize at the boundary, SI float64 within
  engines/     adapter protocols, the subprocess worker, and per-engine adapters
  experiments/ the pure planner, seeding, the runner, the ledger
  metrics/     versioned pure functions; no thresholds live here
  evidence/    package builder and verifier; never imports engines
  analysis/    quarantined: the only place heavy interactive dependencies live
docs/adr/      thirty accepted decision records
```

## Reading the decision records

Start with [ADR-013](docs/adr/ADR-013-package-boundaries.md) for the shape of the codebase, then
[ADR-001](docs/adr/ADR-001-content-addressed-identity.md) and
[ADR-007](docs/adr/ADR-007-evidence-package-format.md) for why the product exists at all.
[ADR-004](docs/adr/ADR-004-uncertainty-belief-model.md) is the scientific heart. Each record
carries per-decision confidence numbers and dated triggers that would make us reverse it —
including the ones we expect to lose.

## License

Not yet determined.
