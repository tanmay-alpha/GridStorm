import warnings

import numpy as np
import pandapower as pp
import pandapower.networks as pn
import pytest
from pandapower.pypower.makeLODF import makeLODF
from pandapower.pypower.makePTDF import makePTDF

from stormbench import dc
from stormbench.matpower import BUS_I, BUS_TYPE, F_BUS, PD, RATE_A, T_BUS, case_from_ppc


def _ppc(name):
    net = getattr(pn, name)()
    pp.rundcpp(net)
    return net._ppc


@pytest.mark.parametrize("name", ["case9", "case14"])
def test_ptdf_lodf_match_pandapower(name):
    ppc = _ppc(name)
    case = case_from_ppc(ppc, name)
    net = dc.build_dc_network(case)
    assert net.n_branch == ppc["branch"].shape[0]
    H = dc.ptdf(net)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        Hpp = makePTDF(ppc["baseMVA"], ppc["bus"], ppc["branch"], slack=net.slack)
        Lpp = makeLODF(ppc["branch"], Hpp)
    np.testing.assert_allclose(H, Hpp, atol=1e-10)
    lr = dc.lodf(net, H)
    ok = ~lr.islanding
    np.testing.assert_allclose(lr.lodf[:, ok], np.asarray(Lpp)[:, ok], atol=1e-10)


@pytest.mark.parametrize("name", ["case9", "case14", "case30"])
def test_lodf_prediction_equals_dc_resolve(name):
    net = dc.build_dc_network(case_from_ppc(_ppc(name), name))
    lr = dc.lodf(net)
    f0 = dc.solve_dc_flows(net)
    outages = np.flatnonzero(~lr.islanding)
    est = dc.post_contingency_flows(f0, lr.lodf)[:, outages]
    exact = dc.dc_n1_resolve(net, outages)
    assert np.max(np.abs(est - exact)) < 1e-6


def test_base_flows_match_pandapower_rundcpp():
    net_pp = pn.case14()
    pp.rundcpp(net_pp)
    ppc = net_pp._ppc
    net = dc.build_dc_network(case_from_ppc(ppc, "case14"))
    np.testing.assert_allclose(dc.solve_dc_flows(net), ppc["branch"][:, 13].real, atol=1e-8)


def _radial_case():
    """Ring 1-2-3-1 plus radial spur 3-4-5; branches 3-4 and 4-5 are bridges."""
    from stormbench.matpower import MatpowerCase

    bus = np.zeros((5, 13))
    bus[:, BUS_I] = [1, 2, 3, 4, 5]
    bus[:, BUS_TYPE] = [3, 1, 1, 1, 1]
    bus[:, PD] = [0, 20, 10, 15, 5]
    gen = np.zeros((1, 10))
    gen[0, [0, 1, 7, 8]] = [1, 50, 1, 100]
    branch = np.zeros((5, 13))
    branch[:, F_BUS] = [1, 2, 3, 3, 4]
    branch[:, T_BUS] = [2, 3, 1, 4, 5]
    branch[:, 3] = [0.1, 0.2, 0.15, 0.1, 0.1]
    branch[:, RATE_A] = 100
    branch[:, 10] = 1
    return MatpowerCase("radial", 100.0, bus, gen, branch)


def test_islanding_detected_on_radial_network():
    net = dc.build_dc_network(_radial_case())
    lr = dc.lodf(net)
    assert lr.islanding.tolist() == [False, False, False, True, True]
    assert (lr.islanding == lr.numeric_islanding).all()
    assert np.isnan(lr.lodf[:, lr.islanding]).all()
    assert np.isfinite(lr.lodf[:, ~lr.islanding]).all()
    eff = dc.island_effect(net, 3)
    assert eff == {"islanded_bus_count": 2, "islanded_net_injection_mw": pytest.approx(-20.0)}


def test_parallel_branches_are_not_bridges():
    f = np.array([0, 0, 1])
    t = np.array([1, 1, 2])
    assert dc.find_bridges(3, f, t).tolist() == [False, False, True]
