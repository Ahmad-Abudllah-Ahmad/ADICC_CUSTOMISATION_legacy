# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Presentation and interchange presets for measurement sheets.

The sheet model is country-neutral. A preset only fixes labelling and the
rounding convention used when a quantity is written out. REB 23.003 (the German
measurement rules, sheets DA11 detailed and DA12 summary) and OENORM A 2063
(the Austrian data exchange) round to three decimals and are the DACH
conventions; the international preset is the sensible default elsewhere. Adding
a convention is one entry in ``PRESETS``.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.modules.measurement.model import MeasurementSheet, _dec


@dataclass(frozen=True)
class Preset:
    name: str
    label: str
    region: str
    decimals: int = 3
    standard: str = ""


_INTERNATIONAL = Preset(
    name="international",
    label="Measurement sheet",
    region="international",
    decimals=3,
    standard="",
)
_REB = Preset(
    name="reb",
    label="REB 23.003 measurement (DA11/DA12)",
    region="DE",
    decimals=3,
    standard="REB 23.003",
)
_OENORM = Preset(
    name="oenorm",
    label="OENORM A 2063 measurement",
    region="AT",
    decimals=3,
    standard="OENORM A 2063",
)

PRESETS: dict[str, Preset] = {p.name: p for p in (_INTERNATIONAL, _REB, _OENORM)}


def get_preset(name: str | None) -> Preset:
    return PRESETS.get((name or "").strip().lower(), _INTERNATIONAL)


def _q(value: Decimal, decimals: int) -> str:
    quant = Decimal(1).scaleb(-decimals)  # 10**-decimals
    return str(_dec(value).quantize(quant, rounding=ROUND_HALF_UP))


def render_markdown(sheet: MeasurementSheet, *, preset: str = "international") -> str:
    """A readable measurement sheet: every line shows its formula and result."""
    p = get_preset(preset)
    out: list[str] = []
    heading = f"# {p.label}: {sheet.item_ref} {sheet.description}".rstrip()
    out.append(heading)
    out.append("")
    out.append(f"Unit: {sheet.unit}")
    out.append("")
    out.append("| Ref | Description | Formula | Factor | Sign | Quantity |")
    out.append("| --- | --- | --- | ---: | :---: | ---: |")
    for ln in sheet.lines:
        formula = ln.formula if not ln.error else f"{ln.formula}  [error: {ln.error}]"
        out.append(
            f"| {ln.ref} | {ln.description} | {formula} | "
            f"{_dec(ln.factor, '1')} | {'-' if str(ln.sign).strip() == '-' else '+'} | "
            f"{_q(ln.raw_quantity, p.decimals)} |"
        )
    out.append("")
    out.append(f"Total quantity: {_q(sheet.total_quantity, p.decimals)} {sheet.unit}")
    return "\n".join(out)


def render_csv(sheet: MeasurementSheet, *, preset: str = "international") -> str:
    """Spreadsheet-friendly measurement sheet (RFC 4180 style quoting)."""
    p = get_preset(preset)
    rows: list[str] = []
    rows.append(_csv_row(["ref", "description", "formula", "factor", "sign", "unit", "quantity", "error"]))
    for ln in sheet.lines:
        rows.append(
            _csv_row(
                [
                    ln.ref,
                    ln.description,
                    ln.formula,
                    str(_dec(ln.factor, "1")),
                    "-" if str(ln.sign).strip() == "-" else "+",
                    ln.unit or sheet.unit,
                    _q(ln.raw_quantity, p.decimals),
                    ln.error,
                ]
            )
        )
    rows.append(_csv_row(["", "TOTAL", "", "", "", sheet.unit, _q(sheet.total_quantity, p.decimals), ""]))
    return "\r\n".join(rows) + "\r\n"


def _csv_row(fields: list[str]) -> str:
    out: list[str] = []
    for raw in fields:
        text = str(raw if raw is not None else "")
        if any(ch in text for ch in (",", '"', "\n", "\r")):
            text = '"' + text.replace('"', '""') + '"'
        out.append(text)
    return ",".join(out)
