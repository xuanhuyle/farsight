# Does `NPY_DISABLE_CPU_FEATURES` do anything?

**Measured 2026-09-08.** ADR-019 decision 3 records the variable names in `ISA_ENV` as
UNVERIFIED. This is the verification, and the answer is no.

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
That change is **not made here**: `ISA_ENV` is inside the hashed environment document, so editing
it moves the predicate, which is a re-golding decision under ADR-019 decision 5. It is also not
obviously the right fix, because the targets are a property of the WHEEL and would have to be
re-derived whenever NumPy is upgraded -- a pin that silently goes stale on a dependency bump is
the same failure mode one level up. Whoever owns that decision should see this paragraph first.

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
