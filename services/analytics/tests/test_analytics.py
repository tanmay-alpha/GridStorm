"""Every analytics kind on PyPSA example networks, checked against independent recomputation
from the raw component tables (not via n.statistics)."""

from __future__ import annotations

import json
import math

import pandas as pd
import pypsa
import pytest

import gridstorm_analytics as ga
from gridstorm_analytics._common import UPSTREAM

NETWORKS = ["ac_dc", "ac_dc_solved", "scigrid", "scigrid_solved"]
SOLVED = ["ac_dc_solved", "scigrid_solved"]
REL = 1e-9


def _net(request: pytest.FixtureRequest, name: str) -> pypsa.Network:
    return request.getfixturevalue(name)


def _group(result: dict, key: str) -> dict:
    return next(g for g in result["groups"] if g["key"] == key)


def _close(a: float, b: float, abs_tol: float = 1e-6) -> bool:
    return math.isclose(a, b, rel_tol=REL, abs_tol=abs_tol)


def _assert_dict_close(got: dict, expected: pd.Series, abs_tol: float = 1e-6) -> None:
    assert set(got) == set(map(str, expected.index)), (sorted(got), sorted(expected.index))
    for k, v in expected.items():
        assert _close(got[str(k)], float(v), abs_tol), (k, got[str(k)], float(v))


# --------------------------------------------------------------------------- API / envelope


def test_available_analytics() -> None:
    kinds = ga.available_analytics()
    assert {"capacity", "energy_balance", "costs", "summary"} <= set(kinds)
    assert tuple(kinds) == ga.KINDS


def test_unknown_kind(ac_dc: pypsa.Network) -> None:
    with pytest.raises(ga.UnknownAnalyticsKind):
        ga.compute("nope", ac_dc)
    assert issubclass(ga.UnknownAnalyticsKind, ValueError)


@pytest.mark.parametrize(
    ("carriers", "countries"),
    [(["coal-that-does-not-exist"], None), ([], None), (None, ["XX"]), (None, [])],
)
def test_invalid_filters(ac_dc: pypsa.Network, carriers, countries) -> None:
    with pytest.raises(ValueError):
        ga.compute("capacity", ac_dc, carriers=carriers, countries=countries)


def test_country_filter_without_country_data(scigrid: pypsa.Network) -> None:
    assert "country" not in scigrid.buses.columns
    with pytest.raises(ValueError, match="no bus country"):
        ga.compute("capacity", scigrid, countries=["DE"])


def test_summary_rejects_filters(ac_dc: pypsa.Network) -> None:
    with pytest.raises(ValueError):
        ga.compute("summary", ac_dc, carriers=["gas"])


@pytest.mark.parametrize("name", NETWORKS)
@pytest.mark.parametrize("kind", ga.KINDS)
def test_envelope_json(request: pytest.FixtureRequest, name: str, kind: str) -> None:
    n = _net(request, name)
    result = ga.compute(kind, n)
    text = json.dumps(result, allow_nan=False)  # strict JSON: no NaN/inf
    assert json.loads(text) == result
    assert result["kind"] == kind
    assert result["provenance"] == "calculated"
    assert result["network_solved"] is bool(n.is_solved)
    assert isinstance(result["assumptions"], list) and result["assumptions"]
    assert result["source"]["upstream"] == "PyPSA-Explorer"
    assert result["source"]["sha"] == UPSTREAM["sha"] and len(UPSTREAM["sha"]) == 40
    assert result["source"]["engine"]["version"] == pypsa.__version__
    assert isinstance(result["units"], dict)
    assert (result["reason"] is None) == result["available"]


# --------------------------------------------------------------------------- capacity


@pytest.mark.parametrize("name", NETWORKS)
def test_capacity_matches_component_tables(request: pytest.FixtureRequest, name: str) -> None:
    n = _net(request, name)
    r = ga.compute("capacity", n)
    assert r["available"] is True

    gen = _group(r, "generator_power")
    _assert_dict_close(
        {c: v["installed_mw"] for c, v in gen["by_carrier"].items()},
        n.generators.groupby("carrier").p_nom.sum(),
    )
    assert r["generation_capacity_by_carrier_mw"] == {
        c: v["installed_mw"] for c, v in gen["by_carrier"].items()
    }
    assert _close(gen["total_installed_mw"], n.generators.p_nom.sum())
    assert _close(_group(r, "line_rating")["total_installed_mva"], n.lines.s_nom.sum())
    if not n.transformers.empty:
        assert _close(
            _group(r, "transformer_rating")["total_installed_mva"], n.transformers.s_nom.sum()
        )
    if not n.links.empty:
        assert _close(_group(r, "link_power")["total_installed_mw"], n.links.p_nom.sum())
    if not n.storage_units.empty:
        su = n.storage_units
        assert _close(_group(r, "storage_unit_power")["total_installed_mw"], su.p_nom.sum())
        assert _close(
            _group(r, "storage_unit_energy")["total_installed_mwh"],
            (su.p_nom * su.max_hours).sum(),
        )

    if n.is_solved:
        _assert_dict_close(
            {c: v["optimal_mw"] for c, v in gen["by_carrier"].items()},
            n.generators.groupby("carrier").p_nom_opt.sum(),
            abs_tol=1e-3,
        )
        assert _close(
            _group(r, "line_rating")["total_optimal_mva"], n.lines.s_nom_opt.sum(), abs_tol=1e-3
        )
    else:
        assert gen["total_optimal_mw"] is None
        assert all(v["optimal_mw"] is None for v in gen["by_carrier"].values())


def test_capacity_rows_sum_to_carrier_totals(ac_dc: pypsa.Network) -> None:
    gen = _group(ga.compute("capacity", ac_dc), "generator_power")
    by_rows: dict[str, float] = {}
    for row in gen["rows"]:
        by_rows[row["carrier"]] = by_rows.get(row["carrier"], 0.0) + row["installed_mw"]
    assert by_rows == pytest.approx({c: v["installed_mw"] for c, v in gen["by_carrier"].items()})


def test_capacity_country_and_carrier_filters(ac_dc: pypsa.Network) -> None:
    gens = ac_dc.generators.assign(country=ac_dc.generators.bus.map(ac_dc.buses.country))
    r = ga.compute("capacity", ac_dc, countries=["DE"])
    assert r["filters"]["countries"] == ["DE"]
    gen = _group(r, "generator_power")
    _assert_dict_close(
        {c: v["installed_mw"] for c, v in gen["by_carrier"].items()},
        gens[gens.country == "DE"].groupby("carrier").p_nom.sum(),
    )
    assert {row["country"] for row in gen["rows"]} == {"DE"}
    lines = ac_dc.lines
    assert _close(
        _group(r, "line_rating")["total_installed_mva"],
        lines[lines.bus0.map(ac_dc.buses.country) == "DE"].s_nom.sum(),
    )

    r = ga.compute("capacity", ac_dc, carriers=["wind"])
    gen = _group(r, "generator_power")
    assert set(gen["by_carrier"]) == {"wind"}
    assert _close(gen["total_installed_mw"], gens[gens.carrier == "wind"].p_nom.sum())


# --------------------------------------------------------------------------- energy balance


@pytest.mark.parametrize("name", ["ac_dc", "scigrid"])
def test_energy_balance_unsolved_unavailable(request: pytest.FixtureRequest, name: str) -> None:
    r = ga.compute("energy_balance", _net(request, name))
    assert r["available"] is False
    assert "not solved" in r["reason"]
    assert r["bus_carriers"] == []


@pytest.mark.parametrize("name", SOLVED)
def test_energy_balance_matches_dispatch(request: pytest.FixtureRequest, name: str) -> None:
    n = _net(request, name)
    r = ga.compute("energy_balance", n)
    assert r["available"] is True
    w = n.snapshot_weightings.generators
    assert r["snapshots"] == [pd.Timestamp(s).isoformat() for s in n.snapshots]
    assert r["snapshot_weightings_h"] == pytest.approx(list(w))

    groups = {g["bus_carrier"]: g for g in r["bus_carriers"]}
    assert set(groups) == set(n.buses.carrier.astype(str))
    assert all(g["unit"] == "MW" for g in groups.values())
    for bc, g in groups.items():
        # Nodal balance: with no filter all rows of a bus carrier sum to ~0 at every snapshot.
        scale = max(1.0, g["supply_mwh"])
        assert abs(g["net_mwh"]) <= 1e-6 * scale, (bc, g["net_mwh"])
        assert g["balance_residual_max_mw"] <= 1e-6 * scale
        assert _close(g["supply_mwh"] + g["withdrawal_mwh"], g["net_mwh"], abs_tol=1e-6 * scale)
        assert _close(sum(g["by_carrier_mwh"].values()), g["net_mwh"], abs_tol=1e-6 * scale)
        # Time series aggregate back to the totals.
        for carrier, ts in g["timeseries_mw"]["by_carrier"].items():
            assert len(ts) == len(n.snapshots)
            total = sum(p * h for p, h in zip(ts, w, strict=True))
            assert _close(total, g["by_carrier_mwh"][carrier], abs_tol=1e-6 * scale)

        # Independent recomputation from generators_t.p / loads_t.p.
        bus_in_bc = n.buses.index[n.buses.carrier.astype(str) == bc]
        gens = n.generators[n.generators.bus.isin(bus_in_bc)]
        gen_mwh = n.generators_t.p[gens.index].mul(w, axis=0).sum().groupby(gens.carrier).sum()
        row_gen: dict[str, float] = {}
        row_load = 0.0
        for row in g["rows"]:
            if row["component"] == "Generator":
                key = row["carrier"] or ""
                row_gen[key] = row_gen.get(key, 0.0) + row["energy_mwh"]
            elif row["component"] == "Load":
                row_load += row["energy_mwh"]
        _assert_dict_close(row_gen, gen_mwh, abs_tol=1e-6 * scale)
        loads = n.loads[n.loads.bus.isin(bus_in_bc)]
        load_mwh = n.loads_t.p[loads.index].mul(w, axis=0).sum().sum()
        assert _close(row_load, -float(load_mwh), abs_tol=1e-6 * scale)


def test_energy_balance_carrier_filter(ac_dc_solved: pypsa.Network) -> None:
    r = ga.compute("energy_balance", ac_dc_solved, carriers=["wind"])
    (g,) = r["bus_carriers"]
    assert set(g["by_carrier_mwh"]) == {"wind"}
    assert g["balance_residual_max_mw"] is None
    gens = ac_dc_solved.generators
    w = ac_dc_solved.snapshot_weightings.generators
    expected = ac_dc_solved.generators_t.p[gens.index[gens.carrier == "wind"]].mul(w, axis=0)
    assert _close(g["by_carrier_mwh"]["wind"], float(expected.sum().sum()))


def test_energy_balance_unit_handling() -> None:
    """PyPSA-Eur energy labels are MW-based; mass carriers are excluded, not mislabelled MWh."""
    n = pypsa.Network()
    n.set_snapshots(range(2))
    n.add("Bus", "el", carrier="AC", unit="MWh_el")
    n.add("Bus", "co2", carrier="co2", unit="t_co2")
    n.add("Generator", "g", bus="el", carrier="gas", p_nom=10, marginal_cost=1)
    n.add("Load", "d", bus="el", carrier="load", p_set=[4.0, 6.0])
    n.add("Store", "atm", bus="co2", carrier="co2", e_nom_extendable=True, e_cyclic=False)
    n.add("Link", "emit", bus0="el", bus1="co2", carrier="emit", p_nom=0, efficiency=0)
    n.optimize(solver_name="highs", solver_options={"threads": 1, "output_flag": False})
    r = ga.compute("energy_balance", n)
    assert [g["bus_carrier"] for g in r["bus_carriers"]] == ["AC"]
    assert r["bus_carriers"][0]["unit"] == "MWh_el"
    assert _close(r["bus_carriers"][0]["by_carrier_mwh"]["gas"], 10.0)
    assert r["excluded_bus_carriers"] == [{"bus_carrier": "co2", "unit": "t_co2"}]


# --------------------------------------------------------------------------- costs


@pytest.mark.parametrize("name", NETWORKS)
def test_costs_match_component_tables(request: pytest.FixtureRequest, name: str) -> None:
    n = _net(request, name)
    r = ga.compute("costs", n)
    assert r["available"] is True
    totals = r["totals"]

    def capex(attr_suffix: str) -> float:
        total = 0.0
        for comp, attr in (
            ("generators", "p_nom"),
            ("links", "p_nom"),
            ("storage_units", "p_nom"),
            ("lines", "s_nom"),
            ("transformers", "s_nom"),
            ("stores", "e_nom"),
        ):
            df = getattr(n, comp)
            if not df.empty:
                total += float((df[attr + attr_suffix] * df.capital_cost).sum())
        return total

    assert _close(totals["capex_installed_eur"], capex(""), abs_tol=1e-3)
    if not n.is_solved:
        assert r["opex_available"] is False and r["opex_reason"]
        assert totals["capex_optimal_eur"] is None and totals["opex_eur"] is None
        assert all(row["opex_eur"] is None for row in r["rows"])
        return

    assert r["opex_available"] is True
    assert _close(totals["capex_optimal_eur"], capex("_opt"), abs_tol=1e-3)
    # Generator OPEX from dispatch x marginal cost, weighted by objective weightings.
    mc = n.get_switchable_as_dense("Generator", "marginal_cost")
    gen_opex = float(
        (n.generators_t.p * mc).mul(n.snapshot_weightings.objective, axis=0).sum().sum()
    )
    row_gen_opex = sum(row["opex_eur"] for row in r["rows"] if row["component"] == "Generator")
    assert _close(row_gen_opex, gen_opex, abs_tol=1e-3)
    # The optimisation objective is total system cost minus the constant CAPEX of
    # non-extendable assets: objective + objective_constant == optimal CAPEX + OPEX.
    assert _close(
        n.objective + n.objective_constant,
        totals["capex_optimal_eur"] + totals["opex_eur"],
        abs_tol=1e-3 * max(1.0, abs(n.objective)),
    )
    by_carrier_sum = sum(v for v in r["by_carrier"]["opex_eur"].values())
    assert _close(by_carrier_sum, totals["opex_eur"], abs_tol=1e-3)


def test_costs_country_filter(ac_dc_solved: pypsa.Network) -> None:
    full = ga.compute("costs", ac_dc_solved)
    parts = [ga.compute("costs", ac_dc_solved, countries=[c]) for c in ("DE", "NO", "UK")]
    for col in ("capex_installed_eur", "capex_optimal_eur", "opex_eur"):
        assert _close(sum(p["totals"][col] for p in parts), full["totals"][col], abs_tol=1e-3), col


# --------------------------------------------------------------------------- summary


@pytest.mark.parametrize("name", NETWORKS)
def test_summary_counts(request: pytest.FixtureRequest, name: str) -> None:
    n = _net(request, name)
    r = ga.compute("summary", n)
    assert r["counts"]["buses"] == len(n.buses)
    assert r["counts"]["generators"] == len(n.generators)
    assert r["counts"]["lines"] == len(n.lines)
    assert r["counts"]["storage_units"] == len(n.storage_units)
    assert r["snapshot_count"] == len(n.snapshots)
    assert r["countries"] == (sorted(set(n.buses.country)) if "country" in n.buses.columns else [])
    if n.is_solved:
        assert _close(r["objective_eur"], n.objective)
    else:
        assert r["objective_eur"] is None
