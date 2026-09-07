"""The geometry provider. ADR-003, ADR-015.

A ``GeometryProvider`` is deliberately **not** an ``Engine`` (ADR-003): it does not step, it holds
no state between calls, and it answers a question about the sky rather than integrating a system.
Treating it as an engine would give it a lifecycle it has no use for and a stepping contract it
cannot honour.

**Every convention comes from the request, and none from this module.** There is no default
aberration correction here, no default frame, and no constant near the top of the file. ADR-015
decision 6 is explicit that a default would be invisible in the evidence package -- the number
changes, the hash changes, and nothing says why. An AST lint refuses any literal aberration string
outside the module that defines the enum, which is what stops one being reintroduced here as a
convenience.

**Coverage is checked per epoch, not assumed.** SPICE does not refuse an epoch outside its
leapsecond table or outside an SPK's window in the way a caller would expect; for the leapsecond
case it extrapolates and returns a plausible number. See ``engines/spice/time.py`` for the
measured cost of that.

**Units are SPICE's own and are declared, never converted here.** CSPICE returns kilometres and
kilometres per second, and this module passes them out with those unit strings attached rather
than converting to SI on the way. ADR-008 puts the conversion at the boundary; a conversion here
would be a second, unhashed place where a number changes.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from farsight.engines.spice.time import check_epoch_covered
from farsight.schemas.errors import UnhonorableSpec
from farsight.schemas.geometry import GeometryRequest

__all__ = [
    "QUANTITY_COMPONENTS",
    "QUANTITY_UNITS",
    "compute",
]

# What each quantity class produces, as (unit, trailing-axis width). Kilometres because that is
# what CSPICE returns; see the module docstring on why nothing is converted here.
QUANTITY_UNITS: dict[str, str] = {
    "range": "km",
    "light_time": "s",
    "direction": "1",
    "state": "km",
}

QUANTITY_COMPONENTS: dict[str, int] = {
    "range": 1,
    "light_time": 1,
    "direction": 3,
    "state": 6,
}


def _spiceypy():
    from farsight.engines.spice.kernels import _spiceypy as _get

    return _get()


def compute(
    request: GeometryRequest,
    epochs: Sequence[float],
    *,
    check_coverage: bool = True,
) -> np.ndarray:
    """Evaluate ``request`` at each epoch. Returns ``(n,)`` or ``(n, components)`` float64.

    ``epochs`` are TDB seconds past J2000 -- ADR-015's ``SimTime``, the float64 the engine boundary
    takes, already converted from the hashed ``Epoch`` by the single conversion point ADR-008
    names. This function does no unit work and no epoch parsing: by the time a value reaches here
    it is a number on the TDB timeline or it is a defect upstream.

    A ``state`` request returns position and velocity together, in that order, because splitting
    them would mean two SPICE calls at the same epoch and therefore two light-time solutions for
    one physical configuration.
    """
    spiceypy = _spiceypy()
    quantity = request.quantity_class
    components = QUANTITY_COMPONENTS[quantity]

    if check_coverage:
        for et in epochs:
            check_epoch_covered(float(et))

    out = np.empty((len(epochs), components), dtype="<f8") if components > 1 \
        else np.empty((len(epochs),), dtype="<f8")

    try:
        for i, raw_epoch in enumerate(epochs):
            et = float(raw_epoch)
            if quantity == "state":
                state, _lt = spiceypy.spkezr(
                    request.target, et, request.frame, request.aberration, request.observer
                )
                out[i, :] = state
            else:
                position, light_time = spiceypy.spkpos(
                    request.target, et, request.frame, request.aberration, request.observer
                )
                if quantity == "range":
                    out[i] = float(spiceypy.vnorm(position))
                elif quantity == "light_time":
                    out[i] = float(light_time)
                else:  # direction
                    norm = float(spiceypy.vnorm(position))
                    if norm == 0.0:
                        # Raised inside the try so the `except UnhonorableSpec: raise`
                        # below re-raises it untouched rather than wrapping it in the
                        # CSPICE-diagnostic message, which would be a lie about the cause.
                        raise UnhonorableSpec(  # noqa: TRY301
                            f"the {request.observer}->{request.target} separation is exactly zero "
                            f"at et={et}, so no direction exists. A unit vector here would be a "
                            f"fabricated answer to a question with none"
                        )
                    out[i, :] = np.asarray(position, dtype="<f8") / norm
    except UnhonorableSpec:
        raise
    except Exception as exc:
        # CSPICE errors carry the diagnostic that says WHICH kernel or body was missing, and it is
        # the most useful sentence in the whole failure. Wrapping without it would replace a
        # precise complaint with a vague one.
        raise UnhonorableSpec(
            f"SPICE could not evaluate {request.quantity_class} for "
            f"{request.observer}->{request.target} in frame {request.frame!r}: {exc}"
        ) from exc

    return out
