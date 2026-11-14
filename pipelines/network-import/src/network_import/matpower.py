"""Minimal, strict parser for MATPOWER version-2 case files (``.m``) as published by PGLib-OPF.

Only the subset used by PGLib-OPF is supported: scalar assignments (``mpc.baseMVA``), numeric
matrices (``mpc.bus``, ``mpc.gen``, ``mpc.branch``, ``mpc.gencost`` ...) and cell arrays of strings
(``mpc.bus_name``). Trailing ``% comment`` text on each matrix row is kept because PGLib uses it to
label the generator fuel class (``NG``, ``COW``, ``NUC``, ``SYNC`` ...). Anything else is rejected
rather than guessed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# MATPOWER column layouts (MATPOWER manual, Appendix B, "caseformat").
BUS_COLS = ("bus_i", "type", "pd", "qd", "gs", "bs", "area", "vm", "va", "base_kv", "zone",
            "vmax", "vmin")
GEN_COLS = ("bus", "pg", "qg", "qmax", "qmin", "vg", "mbase", "status", "pmax", "pmin")
BRANCH_COLS = ("fbus", "tbus", "r", "x", "b", "rate_a", "rate_b", "rate_c", "ratio", "angle",
               "status", "angmin", "angmax")

_SCALAR = re.compile(r"^\s*mpc\.(\w+)\s*=\s*([^\[\{;]+?)\s*;", re.M)
_BLOCK = re.compile(r"^\s*mpc\.(\w+)\s*=\s*([\[\{])(.*?)[\]\}]\s*;", re.M | re.S)


@dataclass
class MatpowerCase:
    name: str
    version: str
    base_mva: float
    bus: list[dict[str, float]]
    gen: list[dict[str, float]]
    branch: list[dict[str, float]]
    gencost: list[list[float]]
    gen_comments: list[str]
    bus_name: list[str] | None = None
    extra_fields: list[str] = field(default_factory=list)


def _split_comment(line: str) -> tuple[str, str]:
    # MATPOWER comments start with '%'; PGLib never uses '%' inside strings on matrix rows.
    if "%" in line:
        data, _, comment = line.partition("%")
        return data, comment.strip()
    return line, ""


def _parse_matrix(body: str) -> tuple[list[list[float]], list[str]]:
    rows: list[list[float]] = []
    comments: list[str] = []
    for raw in body.splitlines():
        data, comment = _split_comment(raw)
        for chunk in data.split(";"):
            tokens = chunk.replace(",", " ").split()
            if not tokens:
                continue
            rows.append([float(t) for t in tokens])
            comments.append(comment)
    return rows, comments


def _parse_cell(body: str) -> list[str]:
    out = []
    for raw in body.splitlines():
        data, _ = _split_comment(raw)
        out.extend(re.findall(r"'([^']*)'", data))
    return out


def _named(rows: list[list[float]], cols: tuple[str, ...], what: str) -> list[dict[str, float]]:
    out = []
    for i, row in enumerate(rows, start=1):
        if len(row) < len(cols):
            raise ValueError(f"{what} row {i} has {len(row)} columns, expected >= {len(cols)}")
        out.append(dict(zip(cols, row[: len(cols)], strict=True)))
    return out


def parse_matpower(path: str | Path) -> MatpowerCase:
    text = Path(path).read_text(encoding="utf-8")
    m = re.search(r"^\s*function\s+mpc\s*=\s*(\w+)", text, re.M)
    if not m:
        raise ValueError(f"{path}: not a MATPOWER case function file")
    name = m.group(1)

    # Strip full-line comments before searching for blocks so commented-out code is ignored.
    body = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("%"))
    scalars = {k: v.strip().strip("'") for k, v in _SCALAR.findall(body)}
    blocks: dict[str, tuple[str, str]] = {k: (kind, b) for k, kind, b in _BLOCK.findall(body)}

    version = scalars.get("version")
    if version != "2":
        raise ValueError(f"{path}: unsupported MATPOWER case version {version!r} (need '2')")
    for required in ("bus", "gen", "branch"):
        if required not in blocks:
            raise ValueError(f"{path}: missing mpc.{required}")

    bus_rows, _ = _parse_matrix(blocks["bus"][1])
    gen_rows, gen_comments = _parse_matrix(blocks["gen"][1])
    branch_rows, _ = _parse_matrix(blocks["branch"][1])
    gencost_rows = _parse_matrix(blocks["gencost"][1])[0] if "gencost" in blocks else []
    bus_name = _parse_cell(blocks["bus_name"][1]) if "bus_name" in blocks else None
    if bus_name is not None and len(bus_name) != len(bus_rows):
        raise ValueError(f"{path}: bus_name has {len(bus_name)} entries for {len(bus_rows)} buses")
    if gencost_rows and len(gencost_rows) not in (len(gen_rows), 2 * len(gen_rows)):
        raise ValueError(f"{path}: gencost rows {len(gencost_rows)} != gen rows {len(gen_rows)}")

    known = {"bus", "gen", "branch", "gencost", "bus_name"}
    return MatpowerCase(
        name=name,
        version=version,
        base_mva=float(scalars["baseMVA"]),
        bus=_named(bus_rows, BUS_COLS, "bus"),
        gen=_named(gen_rows, GEN_COLS, "gen"),
        branch=_named(branch_rows, BRANCH_COLS, "branch"),
        gencost=gencost_rows,
        gen_comments=gen_comments,
        bus_name=bus_name,
        extra_fields=sorted(set(blocks) - known),
    )
