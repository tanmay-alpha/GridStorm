"""Audited cost provenance for the bundled datasets (see cost-basis-audit.md)."""

from __future__ import annotations


def dataset_cost_basis(network_id: str) -> dict:
    common = {
        "schema_version": "gridstorm-cost-basis/1.0",
        "currency": None,
        "currency_year": None,
    }
    if network_id in {"pglib-case14-ieee", "pglib-case118-ieee"}:
        return {
            **common,
            "kind": "benchmark_nominal",
            "money_unit": "PGLib cost units",
            "price_unit": "PGLib cost units/MWh",
            "comparability_key": "pglib-opf-v23.07:nominal-cost:secant-v1",
            "provenance": "PGLib-OPF v23.07 source mpc.gencost uses MATPOWER nominal $/h "
            "polynomial costs; network_import.pglib uses c1 + c2*Pmax, dropping c0.",
            "assumptions": [
                "Benchmark coefficients have no verified currency year or exchange-rate "
                "provenance; they are not EUR or inflation-adjusted USD.",
                "Secant linearisation is exact for linear costs, approximate for quadratic costs; "
                "startup, shutdown and fixed c0 costs are omitted.",
                "VOLL is a scenario penalty in PGLib cost units/MWh, not a monetary estimate "
                "of outage damage.",
            ],
        }
    if network_id in {"ac-dc-meshed", "scigrid-de"}:
        provenance = (
            "PyPSA v1.4.0 ac-dc-meshed toy network contains illustrative generator marginal costs "
            "and generator, line and link capital-cost coefficients."
            if network_id == "ac-dc-meshed"
            else "PyPSA v1.4.0 scigrid-de example uses illustrative per-carrier marginal costs; "
            "the upstream scigrid-lopf-then-pf notebook says these are not accurate."
        )
        return {
            **common,
            "kind": "illustrative",
            "money_unit": "illustrative cost units",
            "price_unit": "illustrative cost units/MWh",
            "comparability_key": f"pypsa-v1.4.0:{network_id}:illustrative-v1",
            "provenance": provenance,
            "assumptions": [
                "Example costs are placeholders, not market prices or a verified currency basis.",
                "Only runs on this same example cost basis are monetarily comparable.",
                "VOLL is a scenario penalty in illustrative cost units/MWh, not an economic "
                "outage-damage estimate.",
            ],
        }
    if network_id == "pypsa-eur-be":
        return {
            **common,
            "kind": "currency_verified",
            "currency": "EUR",
            "currency_year": 2025,
            "money_unit": "EUR",
            "price_unit": "EUR/MWh",
            "comparability_key": "pypsa-eur-v2026.09.0:technology-data-v0.15.0:EUR2025",
            "provenance": "PyPSA-Eur c8209014 tutorial uses technology-data v0.15.0; "
            "its config.yaml declares eur_year: 2025, with costs loaded in EUR by the upstream "
            "electricity build.",
            "assumptions": [
                "EUR 2025 technology assumptions for the 2050 planning horizon, not observed 2013 "
                "electricity prices; currency year differs from weather year and planning year.",
                "Capital costs are annualised and scaled to the objective-weighted horizon; "
                "dispatch-only GridStorm freezes capacities and excludes investment costs.",
                "VOLL is a user-selected penalty in EUR/MWh on this basis, not a calibrated "
                "economic estimate.",
            ],
        }
    return {
        **common,
        "kind": "illustrative",
        "money_unit": "cost units (basis unknown)",
        "price_unit": "cost units (basis unknown)/MWh",
        "comparability_key": f"unverified:{network_id}",
        "provenance": "User-imported network; monetary coefficient provenance has not been "
        "audited.",
        "assumptions": ["No verified currency, currency year or conversion is claimed."],
    }
