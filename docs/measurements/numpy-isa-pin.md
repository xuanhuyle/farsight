# Does `NPY_DISABLE_CPU_FEATURES` do anything?

**Measured 2026-09-08.** ADR-019 decision 3 records the variable names in `ISA_ENV` as
UNVERIFIED. This is the verification. The answer was no; the names were then fixed on the
founder's decision, and the Resolution section at the end records what that did and did not buy.

## What was run

A fresh interpreter per case, because NumPy reads the variable once while importing; asking the
already-imported module cannot answer the question. Local host, Windows, **NumPy 2.5.2**
(`scratchpad/probe_isa3.py`). The container runs **NumPy 2.4.6**, so the same probe was added to
`container/gate_in_image.py` and its result is recorded in `out/gate.json` on every container CI
run. That in-image measurement is Result 1b below, and it does not match the local one.

## Result 1 — the pinned names are rejected, silently

    NPY_DISABLE_CPU_FEATURES=AVX2
      ImportWarning: You cannot disable CPU features (AVX2), since they are not
      part of the dispatched optimizations (X86_V3).

This NumPy dispatches on psABI **group** targets -- `__cpu_baseline__ = ['X86_V2']`,
`__cpu_dispatch__ = ['X86_V3']` -- not on individual feature names. Every one of the six names in
`ISA_ENV` is an individual feature name, so on this wheel every one is rejected.

**The rejection is invisible.** It is an `ImportWarning`, which CPython suppresses by default. A
pin naming features NumPy will not accept therefore behaves identically to a pin that works:
silent, exit 0, no output. The probe passes `-W always::ImportWarning` to see it at all.

## Result 1b -- measured INSIDE the image, and it is worse there

Run 34232188399, NumPy 2.4.6, the manylinux wheel the image actually installs. The dispatch set
is larger than the local wheel's, which changes the answer in a way a laptop could not have shown:

    dispatched optimizations:  X86_V3  X86_V4  AVX512_ICL  AVX512_SPR

    rejected: AVX512F AVX512CD AVX512_SKX AVX512_CLX AVX512_CNL
    accepted: AVX512_ICL   (it happens to be a dispatch target)

Five of the six pinned names are rejected. The sixth, `AVX512_ICL`, is accepted only by accident
of being a target name on this wheel -- so the pin is not uniformly inert, it is *arbitrary*,
which is harder to reason about than uniformly inert.

**And `X86_V4` is a dispatch target in this image.** So on X86_V4 silicon NumPy will dispatch
AVX-512 kernels, and `ISA_ENV` does not stop it: the group names that would stop it (`X86_V4`,
`AVX512_SPR`) are not among the six pinned, and the individual names that are pinned cannot
express it. ADR-019 decision 3 says runtime CPU dispatch "is pinned to a declared baseline". In
this image it is not pinned at all above `X86_V3`.

The names that WOULD work for this wheel are the target names -- `X86_V4 AVX512_ICL AVX512_SPR`.
Applying them was a re-golding decision under ADR-019 decision 5, because `ISA_ENV` is inside the
hashed document. **The founder took that decision on 2026-09-08**; see Resolution below. The
caveat raised at the time stands and is now mechanically covered: the targets are a property of
the WHEEL and would have to be re-derived on a NumPy upgrade, so the gate measures the EFFECT
rather than trusting the names.

A name that does not exist at all (`NOT_A_REAL_FEATURE`) produced no warning and no error, so a
typo in this variable is not detectable from its behaviour either.

## Result 2 — `__cpu_features__` never reflects the variable

| `NPY_DISABLE_CPU_FEATURES` | `AVX2` | `FMA3` | `__cpu_dispatch__` |
| --- | --- | --- | --- |
| unset | True | True | `['X86_V3']` |
| `AVX2 FMA3` | True | True | `['X86_V3']` |
| `NOT_A_REAL_FEATURE` | True | True | `['X86_V3']` |

`__cpu_features__` reports **CPU capability**. It is the source of `isa_enabled_features` in the
Tier-A environment document, via `_isa_features()`.

## What this corrects

Earlier in this project, two GitHub runners produced different predicates, and the diff showed
`isa_enabled_features` gaining 14 AVX-512 entries. That was read as *"the features I listed for
disabling appeared, therefore the ISA pin did not take effect."* **The inference was invalid.**
The field reports what the silicon can do and would have shown those features whether the pin
worked or not. The conclusion happens to be correct, but only for the reason measured above, and
it was not knowable from that diff.

## What it means for the Tier-A predicate

`isa_enabled_features` is inside the hashed environment document, and it tracks CPU identity.
So `numeric_environment_hash` changes when the CPU model changes **whether or not any number
changes**. Measured, same repository state, same day:

    X86_V2, X86_V3              0 AVX-512 features   5754c3748638a8d2...
    X86_V2, X86_V3, X86_V4     14 AVX-512 features   2c6f6b8192ed9d2c...

ADR-019's own Context predicted this shape -- *"an unbudgeted operational requirement that the CI
runner fleet be silicon-homogeneous"* -- as a risk. It is now an observation: GitHub's
`ubuntu-latest` fleet served both generations to this repository within about fifteen minutes.

Three things follow, none of them decided here.

1. The predicate is **stricter than ADR-006 requires**. ADR-006 asks for the same CPU ISA feature
   set; this hashes the full capability list, so it refuses on a CPU change that a correctly
   working ISA pin would have made numerically irrelevant.
2. Enforcing it in CI makes the container job's outcome a function of which machine GitHub
   allocates. That is the *"unpassable for undiagnosable reasons"* failure ADR-006 names, except
   that it is now diagnosable -- `container/fingerprint.json` says exactly which field moved.
3. Fixing the ISA pin is a separate question from fixing the predicate, and neither is a
   number to overwrite. Both are re-golding decisions under ADR-019 decision 5.

## What is still not measured

Whether the geometry itself moves across the two generations. That is DEV-23's question and it
remains open: the only X86_V4 run so far aborted at predicate enforcement before the gate ran,
and before that the gate was executing nothing at all (DEV-20, fourth update). The container job
has since been reordered so the gate runs first, so the next X86_V4 allocation will record its
channel hashes in `out/gate.json` and the comparison becomes possible.

`ISA_RESIDUE` remains true and is untouched by any of this: SPICE geometry is CSPICE arithmetic
over glibc's libm, which neither NumPy's dispatcher nor OpenBLAS's coretype reaches. Even a
working `NPY_DISABLE_CPU_FEATURES` would not constrain the gate's own code path.


## Resolution (2026-09-08)

`ISA_ENV` now reads:

    NPY_DISABLE_CPU_FEATURES = "X86_V4 AVX512_ICL AVX512_SPR"

`X86_V3` is deliberately absent -- it is the declared baseline, and disabling it would drop every
run *below* the level the predicate claims rather than normalizing to it.

**Verified how, given that a wrong name is silent.** Result 2 above is the reason the obvious
check does not work: an unrecognised name is accepted without complaint and changes nothing, so
the absence of a warning proves nothing. `_dispatch_selected()` reports what NumPy actually
selected (`np.lib.introspect.opt_func_info`), that value is recorded in the hashed document as
`isa_dispatch_selected`, and `container/gate_in_image.py` REFUSES a gate run whose selection sits
above the declared baseline -- before any geometry runs, because a refusal issued after the
channels are written is a report about evidence rather than a gate on producing it.

Measured in run 34239183827:

    numpy_rejected_the_pin : False        (the previous six names were rejected)
    dispatch targets       : X86_V3 X86_V4 AVX512_ICL AVX512_SPR    (numpy 2.4.6)
    selected               : X86_V3
    gate                   : HELD -- at or below the declared x86-64-v3 baseline

**The predicate moved, and was re-golded from a measurement.**

    5754c3748638a8d2...  ->  3e63163eb56ec627...

Two independent builds, the second `--no-cache`, produced byte-identical documents, and the new
value was recomputed from the archived artifact rather than copied out of a log.
`container/fingerprint.json` is that artifact's document, copied byte-for-byte.

**What this does NOT establish, and the limit is a real one.** The re-golding run was allocated
**X86_V3 silicon**, where `X86_V3` is what NumPy selects with or without any pin. So what is shown
is that NumPy *accepts* these names and that the selection sits at the baseline -- not that the
pin *changed* anything. Its effect is observable only on silicon that could dispatch above the
baseline, and no such run has happened since the fix.

That is not a gap needing arrangement. The check now fires on its own: the first X86_V4
allocation either reports `selected: X86_V3` -- the pin working, on the hardware where it matters
-- or refuses the gate outright. Both outcomes are informative, and neither can be reached by
reading a log for an absence.

**And it does not touch DEV-23's core point.** SPICE geometry is CSPICE arithmetic over glibc's
libm, which neither NumPy's dispatcher nor OpenBLAS's coretype reaches. `ISA_RESIDUE` is unchanged
and unweakened by any of this: a correctly pinned NumPy still says nothing about the code path the
weeks 1-2 gate actually exercises.

## Postscript (2026-09-08) — two machines, same dispatch, different predicate

The re-golded value failed on the very next run, and the failure is the cleanest evidence yet
that the predicate refuses on the wrong thing.

Run 34239183827 (`3e63163e...`, the re-golded value) against run 34239675707 (`d6957a34...`),
same commit content, same image definition:

| field | run …183827 | run …675707 |
| --- | --- | --- |
| `isa_enabled_features` | +16 entries: AVX512BF16, AVX512BITALG, AVX512BW, AVX512CD, AVX512DQ, AVX512F, AVX512FP16, AVX512IFMA, AVX512VBMI, AVX512VBMI2, AVX512VL, AVX512VNNI, AVX512VPOPCNTDQ, AVX512_CLX, AVX512_CNL, GFNI | — |
| **`isa_dispatch_selected`** | **`['X86_V3']`** | **`['X86_V3']`** |
| `interpreter`, `mapped_libraries`, `blas`, `uv_lock_sha256`, `isa_env`, `thread_env`, `engine_build_ids`, `isa_baseline`, `schema_version` | identical | identical |

**Exactly one field differs, and it is not one that changes which code runs.** The two machines
select the same NumPy kernels, map the same libm and the same CSPICE, run the same interpreter
binary and resolve the same lock file. The predicate refuses anyway, because CPU capability is
inside the hashed half.

That is no longer a prediction from ADR-019's Context, nor an inference from a single mismatch. It
is a two-machine measurement in which every determinant of the numbers agrees and the predicate
disagrees. ADR-019's own falsifier for the predicate is stated in the other direction -- a bitwise
mismatch where the predicates AGREE, which would mean a field is missing. This is the opposite
failure: a field is present that should not be.

**Three GitHub runner shapes have now been seen in one day**, all `ubuntu-latest`:

    X86_V2 X86_V3         0 AVX-512      run 34239675707
    X86_V2 X86_V3        15 AVX-512      run 34239183827
    X86_V2 X86_V3 X86_V4 14 AVX-512      run 34214034902

So no single pinned value can hold. Re-golding to whichever shape ran last is whack-a-mole, and
each round would report a green check that means only "the same lottery ticket came up twice".

**A reporting defect this exposed, fixed here.** The gate's summary line printed
`x86 level: X86_V2, X86_V3` for the first two shapes above -- identical text for machines
differing by 16 AVX-512 entries -- and that line was read as "same machine". The line now carries
the AVX-512 count. A summary that omits the field the predicate refuses on is worse than none.

**Not decided here.** Whether `isa_enabled_features` belongs in the hashed half at all is an
ADR-019 decision 5 / ADR-006 question with a named owner, and it changes what a Tier-A claim
means. The measurement is recorded; the decision is not taken.
