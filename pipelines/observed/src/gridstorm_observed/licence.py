"""Licence gate for the Data Observatory bundle (``data/observatory/``).

A series may be written into the bundle only if its *source key* (``<source>:<column/parameter>``)
is on the explicit allow-list :data:`ALLOWED` with a licence record whose redistribution is
``permitted``. Restricted sources can never pass, even if someone adds them to the allow-list:
:func:`is_restricted` is checked first and matches the ENTSO-E actual load (Reg. 543/2013
Art. 6.1.a), every actual-generation column (Art. 16.1) and every capacity column (OPSD
calculations on BNetzA/netztransparenz.de data without a declared licence); see
``docs/research/entsoe-reuse-check.md``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import sources

POWER_SOURCE = "nasa-power"
OPSD_SOURCE = "opsd"
DERIVED_SOURCE = "gridstorm-derived"


class LicenceError(ValueError):
    """A series or text would publish data that is not on the licence allow-list."""


@dataclass(frozen=True)
class LicenceRecord:
    source_key: str
    licence_id: str
    licence_name: str
    licence_url: str
    redistribution: str
    basis: str


#: Patterns that can never be published, whatever the allow-list says.
RESTRICTED_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"load_actual", re.IGNORECASE),
    re.compile(r"generation_actual", re.IGNORECASE),
    re.compile(r"capacity", re.IGNORECASE),
    re.compile(r"renewable_daily_multiplier", re.IGNORECASE),
)
#: Exact column names that must not appear anywhere in a published file.
RESTRICTED_NAMES: tuple[str, ...] = sources.OPSD_NON_OPEN_COLUMNS

_POWER_BASIS = (
    "NASA Earthdata data-use guidance: unless marked with a use restriction or licence, data "
    "from NASA-led missions are CC0 and may be reproduced and distributed without permission, "
    "with NASA acknowledged as the source and no implied endorsement. POWER pages mark no "
    "restriction; the POWER referencing guide asks for the project reference, service name, "
    "version and access date, and requests notification of redistribution."
)
_FORECAST_BASIS = (
    f"ENTSO-E list of data available for free re-use ({sources.ENTSOE_REUSE_LIST_VERSION}, "
    f"sha256 {sources.ENTSOE_REUSE_LIST_SHA256}), item #1 = Reg. (EU) 543/2013 Art. 6.1.b "
    "day-ahead total load forecast: CC BY 4.0 with attribution and indication of changes."
)


def _power(param: str) -> LicenceRecord:
    return LicenceRecord(
        source_key=f"{POWER_SOURCE}:{param}",
        licence_id="LicenseRef-NASA-POWER",
        licence_name="NASA open data (no use restriction marked) + POWER referencing guide",
        licence_url=sources.POWER_DATA_USE_URL,
        redistribution="permitted",
        basis=_POWER_BASIS,
    )


#: The allow-list. Adding a key here is a licence decision: record the evidence in ``basis``
#: and in ``docs/data/sources-and-licensing.md``.
ALLOWED: dict[str, LicenceRecord] = {
    f"{OPSD_SOURCE}:{sources.OPSD_LOAD_FORECAST_COL}": LicenceRecord(
        source_key=f"{OPSD_SOURCE}:{sources.OPSD_LOAD_FORECAST_COL}",
        licence_id="CC-BY-4.0",
        licence_name="Creative Commons Attribution 4.0 International",
        licence_url=sources.CC_BY_4_URL,
        redistribution="permitted",
        basis=_FORECAST_BASIS,
    ),
    f"{DERIVED_SOURCE}:demand_multipliers": LicenceRecord(
        source_key=f"{DERIVED_SOURCE}:demand_multipliers",
        licence_id="CC-BY-4.0",
        licence_name="Creative Commons Attribution 4.0 International",
        licence_url=sources.CC_BY_4_URL,
        redistribution="permitted",
        basis=(
            "Hourly demand multipliers computed only from the CC BY 4.0 day-ahead load forecast "
            "and the scigrid-de network load (CC BY 4.0). " + _FORECAST_BASIS
        ),
    ),
    **{f"{POWER_SOURCE}:{p}": _power(p) for p in ("T2M", "WS10M", "WS50M", "ALLSKY_SFC_SW_DWN")},
}


def is_restricted(source_key: str) -> bool:
    column = source_key.split(":", 1)[-1]
    if column in RESTRICTED_NAMES or source_key in RESTRICTED_NAMES:
        return True
    return any(p.search(source_key) for p in RESTRICTED_PATTERNS)


def gate(source_key: str, allowed: dict[str, LicenceRecord] | None = None) -> LicenceRecord:
    """The licence record for ``source_key``; raises :class:`LicenceError` unless publishable."""
    if is_restricted(source_key):
        raise LicenceError(f"{source_key}: restricted source, never published")
    record = (ALLOWED if allowed is None else allowed).get(source_key)
    if record is None:
        raise LicenceError(f"{source_key}: not on the licence allow-list")
    if record.redistribution != "permitted":
        raise LicenceError(f"{source_key}: redistribution is {record.redistribution!r}")
    return record


def assert_clean_text(name: str, text: str) -> None:
    """Fail if a published file names a restricted column."""
    for col in RESTRICTED_NAMES:
        if col in text:
            raise LicenceError(f"{name} names restricted column {col}")
    for word in ("load_actual", "generation_actual"):
        if word in text:
            raise LicenceError(f"{name} contains restricted token {word}")
