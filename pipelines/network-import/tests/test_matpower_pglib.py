import math
from pathlib import Path

import pytest

from network_import.matpower import parse_matpower
from network_import.paths import networks_dir
from network_import.pglib import UNLIMITED_RATING_MVA, build_network, schematic_layout

MINI = """\
function mpc = mini
mpc.version = '2';
mpc.baseMVA = 100.0;
%% bus data
mpc.bus = [
	1	 3	 0.0	 0.0	 0.0	 0.0	 1	 1.0	 0.0	 138.0	 1	 1.06	 0.94;
	2	 1	 90.0	 30.0	 5.0	 19.0	 1	 1.0	 0.0	 138.0	 1	 1.06	 0.94;
	3	 2	 0.0	 0.0	 0.0	 0.0	 1	 1.0	 0.0	 345.0	 1	 1.06	 0.94;
];
mpc.gen = [
	1	 50.0	 0.0	 10.0	 -10.0	 1.0	 100.0	 1	 200.0	 20.0; % NG
	3	 40.0	 0.0	 10.0	 -10.0	 1.0	 100.0	 0	 100.0	 0.0; % COW
];
mpc.branch = [
	1	 2	 0.01	 0.1	 0.02	 150.0	 0.0	 0.0	 0.0	 0.0	 1	 -30.0	 30.0;
	2	 3	 0.0	 0.05	 0.0	 0.0	 0.0	 0.0	 0.98	 0.0	 1	 -30.0	 30.0;
];
mpc.gencost = [
	2	 0.0	 0.0	 3	 0.01	 10.0	 5.0;
	2	 0.0	 0.0	 3	 0.0	 20.0	 0.0;
];
"""


@pytest.fixture()
def mini_case(tmp_path: Path):
    p = tmp_path / "mini.m"
    p.write_text(MINI, encoding="utf-8")
    return parse_matpower(p)


def test_parser_reads_blocks_and_comments(mini_case):
    assert mini_case.base_mva == 100.0
    assert [b["bus_i"] for b in mini_case.bus] == [1, 2, 3]
    assert mini_case.gen_comments == ["NG", "COW"]
    assert mini_case.branch[1]["ratio"] == 0.98
    assert len(mini_case.gencost) == 2


def test_parser_rejects_version_1(tmp_path: Path):
    p = tmp_path / "old.m"
    p.write_text(MINI.replace("'2'", "'1'"), encoding="utf-8")
    with pytest.raises(ValueError, match="version"):
        parse_matpower(p)


def test_build_units_ids_and_flags(mini_case):
    n, rep = build_network(mini_case, "mini")
    c = n.c
    assert list(c.buses.static.index) == ["bus-1", "bus-2", "bus-3"]
    assert list(c.lines.static.index) == ["branch-1"]
    assert list(c.transformers.static.index) == ["branch-2"]  # tap 0.98 and 138/345 kV
    assert list(c.generators.static.index) == ["gen-1", "gen-2"]
    assert list(c.loads.static.index) == ["load-2"]
    line = c.lines.static.loc["branch-1"]
    assert math.isclose(line.x, 0.1 * 138.0**2 / 100.0)
    assert math.isclose(line.r, 0.01 * 138.0**2 / 100.0)
    assert math.isclose(line.b, 0.02 * 100.0 / 138.0**2)
    tr = c.transformers.static.loc["branch-2"]
    assert tr.s_nom == UNLIMITED_RATING_MVA and rep.unlimited_branches == ["branch-2"]
    assert math.isclose(tr.x, 0.05 * UNLIMITED_RATING_MVA / 100.0)  # re-based to s_nom
    assert tr.tap_ratio == 0.98
    g = c.generators.static
    assert math.isclose(g.loc["gen-1", "marginal_cost"], 10.0 + 0.01 * 200.0)  # secant
    assert g.loc["gen-1", "control"] == "Slack" and g.loc["gen-1", "carrier"] == "NG"
    assert math.isclose(g.loc["gen-1", "p_min_pu"], 0.1)
    assert not g.loc["gen-2", "active"] and rep.out_of_service_gens == ["gen-2"]
    assert rep.quadratic_cost_gens == ["gen-1"] and rep.nonzero_gs_buses == ["bus-2"]
    assert math.isclose(c.shunt_impedances.static.loc["shunt-2", "b"], 19.0 / 138.0**2)


def test_layout_is_deterministic(mini_case):
    n, _ = build_network(mini_case, "mini")
    assert schematic_layout(n).equals(schematic_layout(n))


@pytest.mark.parametrize("nid,counts", [
    ("pglib-case14-ieee", (14, 20, 5)),
    ("pglib-case118-ieee", (118, 186, 54)),
])
def test_committed_sources_parse(nid, counts):
    src = next((networks_dir() / nid / "source").glob("*.m"))
    case = parse_matpower(src)
    assert (len(case.bus), len(case.branch), len(case.gen)) == counts


def test_case14_dc_powerflow_balances():
    case = parse_matpower(networks_dir() / "pglib-case14-ieee/source/pglib_opf_case14_ieee.m")
    n, _ = build_network(case, "case14")
    n.lpf()
    gen = float(n.c.generators.dynamic["p"].iloc[0].sum())
    load = float(n.c.loads.dynamic["p"].iloc[0].sum())
    assert math.isclose(load, sum(b["pd"] for b in case.bus))
    assert math.isclose(gen, load, rel_tol=1e-9)
