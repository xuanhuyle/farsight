# What FarSight has checked, and what it found

**Status: internally cross-checked; not externally expert-reviewed** ([ADR-030](docs/adr/)). Nothing
below has been reviewed by a domain expert, and that is stated rather than glossed. The absence of
an expert reviewer widens the uncertainty here; it does not lower the bar for what gets claimed.

---

## The problem this addresses

A deep-space mission cannot be repaired, revisited, or re-run. Decisions about one are made from
written analyses — link budgets, thermal models, reliability estimates — and almost none of those
analyses are ever independently rebuilt. They are read, believed, and cited.

The gap that matters is not between right and wrong. It is between **what a document actually
establishes** and **what a reader assumes it establishes**. A published analysis can be entirely
competent and still rest on a convention its author never wrote down, because it was obvious to
them at the time. Ten years later that convention is invisible, and the number it produced looks
like a measurement.

FarSight exists to tell those apart. Its working method is to take a published analysis and rebuild
it from the inputs the document itself prints — nothing else, no filling in gaps — and then report
exactly where the rebuild diverges. A divergence is not an accusation. It is a map of what the
document leaves unsaid.

Two rules make that method mean something:

1. **The standard is fixed before the answer is known.** What counts as success is written down and
   committed first, so a result cannot be graded against a target adjusted to fit it.
2. **A miss is reported with the input responsible, never closed by adjusting an input.** Tuning a
   value until the answer matches is how a reproduction becomes a restatement.

---

## Three cases

### 1. Voyager 2, 1996 — a published link budget

**The source.** JPL's own *Voyager Telecommunications* (DESCANSO Series, Article 4, 2002), which
prints design control tables predicting Voyager 2's radio link at the 70 m Canberra antenna on
1 January 1996, plus a table of the spacecraft's predicted path across the sky.

**What was asked.** Can the printed totals be reproduced by summing the printed rows — and can the
predicted sky path be reproduced from today's orbital data?

**What happened.** Neither, to the precision the document prints. The arithmetic misses by **0.4 dB**
or less; the sky path by **0.023°** or less. Both are small. Neither is zero.

**What was never written down.** The document's own tables do not share one convention: no single
declared rule reproduces more than **9 of 15** printed totals, while allowing a different rule per
table reaches **13 of 15**. And the sky-path residuals are not noise — they flip sign at the top of
the pass, the signature of a small time offset. Fitting one gives **+5.59 s**, which collapses the
error to **0.0059°**, about the table's own printing precision.

That last number is reported as a diagnostic, not a success: it was fitted to the very residuals it
removes, so accepting it would be tuning the answer to the question. The cause remains unknown.

### 2. NASA's live DSN feed — an experiment that failed

**The source.** NASA's public "DSN Now" feed, which reports in real time which antennas are talking
to which spacecraft, and at what signal strength.

**What was asked.** Could that feed serve as an answer key — real measurements to score a link
calculation against? The test was written down first: compare a big dish against a smaller one
talking to the same spacecraft on the same day, where physics demands a difference of roughly 5.7 to
6.7 dB. The pass band was fixed in advance at **[3.3, 9.0] dB**, deliberately generous.

**What happened.** **0 of 8** qualifying comparisons landed in that band. Every single difference was
exactly 0 or exactly 10 dB.

**Why.** The feed reports deep-space signal strength in 10 dB steps — **97%** of eligible readings sit
on multiples of ten. The field is a coarse category, not a measurement. It is entirely fit for the
public display it was built for, and useless as a scoring key.

**This is the most useful of the three results**, for an unobvious reason: the project committed to a
test that could fail, and it failed. The logging was shut off the same day the verdict was written,
after **4,285** snapshots. A method that only ever confirms things is not a method.

### 3. Pioneer 10 and 11 — a famous anomaly, and the paper that explains it

**The source.** Two 1970s probes drifted very slightly off their predicted course for decades. For
years it was an open question whether the laws of gravity needed amending. The leading mundane
explanation is that heat radiating unevenly off the spacecraft pushed it — and one well-cited paper
([arXiv:1103.5222](https://arxiv.org/abs/1103.5222)) works that out in detail.

**What was asked.** Do the paper's headline numbers follow from the inputs it prints?

**What happened.** Mostly yes, strikingly so — and then not.

| Scenario | Paper says | Rebuild gives |
|---|---|---|
| 1–4 | 2.27, 4.43, 5.71, 5.69 | 2.2721, 4.4341, 5.7115, 5.6881 |
| 5 (upper bound) | **6.71** | **6.9166** |

Four rebuild to four significant figures. The fifth is 3% off, and **no input stated anywhere in the
paper closes that gap.** Separately, the paper's headline statistical result of **5.8 ± 1.3** rebuilds
as **5.7044** ± **1.1875** — and the paper's own figure sits above the very scenario it is centred
on, which averaging around that scenario cannot produce.

**What was never written down.**

- One input appears with no derivation at all. It turns out to be simply the RTG power divided by
  **1/14** of the cylinder's surface — geometry, recoverable — giving **144.57** W against the
  published 143.86 W. Inverted, the published figure implies an RTG power of **2014** W where the
  paper states 2024 W.
- The paper's public claim that this explains "**44% to 96%**" of the anomaly only follows if the
  anomaly's own error bar is swung against the model at each end. Doing that here gives
  **45% to 93%**. The paper does not say it does this.
- The paper carries two different plutonium half-lives, in its prose and in its equation. The
  difference is immaterial — 0.005% — and is recorded because it was found, not because it matters.

---

## Findings at a glance

Every number here appears in the memo cited beside it, and a test enforces that.

| Finding | Number | Source |
|---|---|---|
| Voyager link arithmetic, worst residual | 0.4 dB | [experiments/voyager_dct/VOYAGER_DCT_RESULT.md](experiments/voyager_dct/VOYAGER_DCT_RESULT.md) |
| Voyager sky path, worst residual | 0.023° | [experiments/voyager_dct/VOYAGER_DCT_RESULT.md](experiments/voyager_dct/VOYAGER_DCT_RESULT.md) |
| Best single convention across the tables | 9 of 15 | [experiments/voyager_dct/VOYAGER_DCT_RESULT.md](experiments/voyager_dct/VOYAGER_DCT_RESULT.md) |
| A different convention per table | 13 of 15 | [experiments/voyager_dct/VOYAGER_DCT_RESULT.md](experiments/voyager_dct/VOYAGER_DCT_RESULT.md) |
| Apparent time offset in the pass table | +5.59 s | [experiments/voyager_dct/VOYAGER_DCT_RESULT.md](experiments/voyager_dct/VOYAGER_DCT_RESULT.md) |
| Residual after that offset | 0.0059° | [experiments/voyager_dct/VOYAGER_DCT_RESULT.md](experiments/voyager_dct/VOYAGER_DCT_RESULT.md) |
| DSN feed comparisons inside the pre-registered band | 0 of 8 | [experiments/dsn_now_probe/RESULT.md](experiments/dsn_now_probe/RESULT.md) |
| The band, fixed before collection | [3.3, 9.0] dB | [experiments/dsn_now_probe/RESULT.md](experiments/dsn_now_probe/RESULT.md) |
| Eligible readings on multiples of ten | 97% | [experiments/dsn_now_probe/RESULT.md](experiments/dsn_now_probe/RESULT.md) |
| Snapshots collected before logging stopped | 4,285 | [experiments/dsn_now_probe/RESULT.md](experiments/dsn_now_probe/RESULT.md) |
| Pioneer upper bound, published | 6.71 | [experiments/pioneer_thermal/RESULT.md](experiments/pioneer_thermal/RESULT.md) |
| Pioneer upper bound, rebuilt | 6.9166 | [experiments/pioneer_thermal/RESULT.md](experiments/pioneer_thermal/RESULT.md) |
| Pioneer statistical centre, rebuilt | 5.7044 | [experiments/pioneer_thermal/RESULT.md](experiments/pioneer_thermal/RESULT.md) |
| Pioneer statistical half-width, rebuilt | 1.1875 | [experiments/pioneer_thermal/RESULT.md](experiments/pioneer_thermal/RESULT.md) |
| The undocumented input, as a share of RTG area | 1/14 | [experiments/pioneer_thermal/RESULT.md](experiments/pioneer_thermal/RESULT.md) |
| That input, reconstructed | 144.57 | [experiments/pioneer_thermal/RESULT.md](experiments/pioneer_thermal/RESULT.md) |
| RTG power implied by the published value | 2014 | [experiments/pioneer_thermal/RESULT.md](experiments/pioneer_thermal/RESULT.md) |
| Published share of the anomaly explained | 44% to 96% | [experiments/pioneer_thermal/RESULT.md](experiments/pioneer_thermal/RESULT.md) |
| The same share, rebuilt under that convention | 45% to 93% | [experiments/pioneer_thermal/RESULT.md](experiments/pioneer_thermal/RESULT.md) |

---

## What none of this licenses

This section is not a disclaimer. It is the part of the work that the rest depends on.

- **No published paper here is shown to be wrong.** Every result is a difference between a
  document's printed numbers and a rebuild from its printed inputs. An unstated convention explains
  such a difference just as well as an error does, and in the Voyager case that is the more likely
  reading. A transcription slip into a table and a mistake in my rebuild produce identical evidence.
- **No claim of external validation.** This work is internally cross-checked and literature-
  supported. It has not been expert-reviewed, independently validated, certified, or flight
  qualified, and internal auditability is not a substitute for any of those.
- **Nothing here tests whether the underlying physics is right.** In the Pioneer case specifically,
  the paper's geometric coefficients were taken as printed and used as inputs. Whether they follow
  from the spacecraft's shape is untested — and one part of that test is blocked outright, because
  the reflection parameter the paper's specular terms depend on is never stated in it.
- **Nothing here resolves the Pioneer anomaly.** The strongest evidence for the thermal explanation
  comes from an independent analysis built on flight telemetry and design documentation, which is
  out of reach here and was never a target.
- **Two Pioneer figures rest on an assumption of mine, not on printed values** — the results at 8 and
  17 years after launch use input splits scaled from the one epoch the paper documents fully,
  because it does not print the others. They agree with the published values; that agreement is
  weaker evidence than it looks, and the memo says so.

---

## How to check any of this yourself

Each result is a script, a memo, and a record of what counted as success before the answer existed.

```bash
python experiments/pioneer_thermal/reproduce_thermal_acceleration.py --alternatives
```

Exit code 1 *is* the verdict there — 0 would mean both criteria passed. `--alternatives` prints
every other reading of the paper that was tried and rejected, so the search is inspectable rather
than asserted.

**On the ordering of criteria and results**, which is the whole basis for trusting a stated
standard:

| Case | Criteria fixed in | Result in | Provable from git? |
|---|---|---|---|
| DSN feed probe | `c500ccf`, 2026-09-10 | `ca6f429`, 2026-09-28 | **Yes** — 18 days apart |
| Pioneer | `934505e`, 2026-09-28 | `d8f8ba7`, 2026-09-28 | **Yes** — separate, earlier commit |
| Voyager | script docstrings | `6c2b5ba`, 2026-09-10 | **No** — same commit |

For Voyager the criteria were written before the script first ran, but they landed in the same
commit as the result, so that ordering rests on my account of it rather than on the repository. The
two later experiments were done differently on purpose, and that is why the pre-registration is now
always its own commit.

---

## What is next

The open thread is the one the Pioneer work deliberately did not touch: deriving those geometric
coefficients from the spacecraft's shape, rather than taking them as printed. It is the deepest
available test of that paper, and it is partly impossible for anyone — the missing reflection
parameter is missing from the source itself. Establishing that cleanly would be a finding in its
own right.
