"""Analytical DC regressions and physical/integrity checks on the actual two-engine runs.

Invoked last by run_all.py; can also run in the importer's environment after generating _work/.
No mocked engine outputs are used by the integration checks.
"""

from __future__ import annotations

import copy
import json
import math
import sys
import unittest
from pathlib import Path

import compare
import mpc
import numpy as np

CASE_IDS = list(mpc.CASES)


def triangle() -> dict:
    """100 MW through three equal-reactance branches: 2/3 direct, 1/3 indirect."""
    bus = np.zeros((3, 13))
    bus[:, mpc.BUS_I] = [1, 2, 3]
    bus[:, mpc.BUS_TYPE] = [3, 1, 1]
    bus[:, mpc.BASE_KV] = 100
    bus[1, mpc.PD] = 100
    gen = np.zeros((1, 10))
    gen[0, [mpc.GEN_BUS, mpc.PG, mpc.GEN_STATUS, mpc.PMAX]] = [1, 100, 1, 200]
    branch = np.zeros((3, 13))
    branch[:, mpc.F_BUS] = [1, 1, 3]
    branch[:, mpc.T_BUS] = [2, 3, 2]
    branch[:, mpc.BR_X] = 0.1
    branch[:, mpc.BR_STATUS] = 1
    branch[:, mpc.RATE_A] = 200
    return {"baseMVA": 100.0, "bus": bus, "gen": gen, "branch": branch}


class AnalyticalPhysicsTests(unittest.TestCase):
    def test_equal_reactance_mesh_splits_power_two_to_one(self):
        case = triangle()
        dc = mpc.reference_dcpf(case, mpc.fixed_dispatch(case))
        np.testing.assert_allclose(
            list(dc["branch_flow_mw"].values()), [200 / 3, 100 / 3, 100 / 3], atol=1e-10
        )
        self.assertAlmostEqual(dc["bus_angle_deg"]["bus-2"], math.degrees(-1 / 15))
        self.assertAlmostEqual(dc["bus_angle_deg"]["bus-3"], math.degrees(-1 / 30))

    def test_tap_and_phase_shift_redistribute_mesh_flow(self):
        case = triangle()
        case["branch"][0, mpc.TAP] = 2
        case["branch"][0, mpc.SHIFT] = math.degrees(0.01)
        dc = mpc.reference_dcpf(case, mpc.fixed_dispatch(case))
        # KCL: F_direct + F_path = 100. KVL: .002 F_direct + .01 = .002 F_path.
        np.testing.assert_allclose(
            list(dc["branch_flow_mw"].values()), [47.5, 52.5, 52.5], atol=1e-10
        )

    def test_original_pg_slack_and_balanced_dispatch_are_distinct(self):
        case = triangle()
        case["gen"][0, mpc.PG] = 60
        raw = mpc.fixed_dispatch(case, balance=False)
        balanced = mpc.fixed_dispatch(case)
        self.assertEqual(raw["gen_p_mw"]["gen-1"], 60)
        self.assertEqual(balanced["gen_p_mw"]["gen-1"], 100)
        dc = mpc.reference_dcpf(case, raw)
        self.assertAlmostEqual(dc["slack_mismatch_mw"], 40)
        self.assertAlmostEqual(sum(dc["bus_injection_mw"].values()), 0)

    def test_injection_disagreement_fails_even_if_flows_match(self):
        case = triangle()
        a = mpc.reference_dcpf(case, mpc.fixed_dispatch(case))
        b = copy.deepcopy(a)
        b["bus_injection_mw"]["bus-2"] += 0.1
        check = compare._dcpf_check(
            "test",
            "triangle",
            a,
            b,
            ("a", "b"),
            list(a["bus_angle_deg"]),
            list(a["branch_flow_mw"]),
        )
        self.assertEqual(check["verdict"], "DISAGREES")

    def test_nonfinite_data_cannot_produce_agreement(self):
        with self.assertRaises(ValueError):
            compare._diff_metrics({"branch-1": float("nan")}, {"branch-1": 1}, ["branch-1"])

    def test_equal_objective_does_not_establish_dispatch_agreement(self):
        a, b = {"gen_p_mw": {"gen-1": 10}}, {"gen_p_mw": {"gen-1": 11}}
        c = compare._opf_check("test", "triangle", a, b, ("a", "b"), 100, 100, "")
        self.assertEqual(c["verdict"], "DISAGREES")


class ObservedEngineTests(unittest.TestCase):
    def records(self):
        for nid in CASE_IDS:
            case = mpc.load_case(mpc.source_path(nid))
            pp = mpc.read_json(mpc.WORK / f"{nid}.pandapower.json")
            py = mpc.read_json(mpc.WORK / f"{nid}.pypsa.json")
            yield nid, case, pp, py

    def nodal_branch_injections(self, case, flows, receiving=None):
        injection = {mpc.bus_id(b[mpc.BUS_I]): 0.0 for b in case["bus"]}
        for i, branch in enumerate(case["branch"]):
            bid = mpc.branch_id(i)
            f, t = mpc.bus_id(branch[mpc.F_BUS]), mpc.bus_id(branch[mpc.T_BUS])
            injection[f] += flows[bid]
            injection[t] += receiving[bid] if receiving is not None else -flows[bid]
        return injection

    def test_both_dispatches_obey_kcl_kvl_and_original_inputs(self):
        for nid, case, pp, py in self.records():
            for name, side in (("pandapower", pp), ("pypsa", py)):
                for dc_key, dispatch_key in (("dc", "dispatch"), ("raw_dc", "raw_dispatch")):
                    with self.subTest(case=nid, engine=name, dispatch=dispatch_key):
                        dc, dispatch = side[dc_key], side[dispatch_key]
                        kcl = self.nodal_branch_injections(case, dc["branch_flow_mw"])
                        scheduled = {k: 0.0 for k in kcl}
                        for i, gen in enumerate(case["gen"]):
                            gid = mpc.gen_id(i)
                            p = dc["gen_p_mw"][gid]
                            if gid != dispatch["slack_gen"]:
                                self.assertAlmostEqual(p, dispatch["gen_p_mw"][gid], delta=1e-6)
                            scheduled[mpc.bus_id(gen[mpc.GEN_BUS])] += p
                        for bus in case["bus"]:
                            k = mpc.bus_id(bus[mpc.BUS_I])
                            scheduled[k] -= bus[mpc.PD] + bus[mpc.GS]
                            self.assertAlmostEqual(kcl[k], scheduled[k], delta=1e-6)
                            self.assertAlmostEqual(kcl[k], dc["bus_injection_mw"][k], delta=1e-6)
                        for i, br in enumerate(case["branch"]):
                            f, t = mpc.bus_id(br[mpc.F_BUS]), mpc.bus_id(br[mpc.T_BUS])
                            angle = math.radians(
                                dc["bus_angle_deg"][f] - dc["bus_angle_deg"][t] - br[mpc.SHIFT]
                            )
                            expected = (
                                case["baseMVA"] * angle / (br[mpc.BR_X] * (br[mpc.TAP] or 1))
                                if br[mpc.BR_STATUS]
                                else 0.0
                            )
                            self.assertAlmostEqual(
                                dc["branch_flow_mw"][mpc.branch_id(i)], expected, delta=1e-6
                            )

    def test_opf_obeys_kcl_bounds_ratings_and_actual_cost(self):
        for nid, case, pp, py in self.records():
            for name, side in (("pandapower", pp), ("pypsa", py)):
                with self.subTest(case=nid, engine=name):
                    opf = side["dcopf"]
                    self.assertTrue(opf.get("converged") or opf.get("status") == "ok")
                    kcl = self.nodal_branch_injections(case, opf["branch_flow_mw"])
                    scheduled = {k: 0.0 for k in kcl}
                    objective = 0.0
                    for i, gen in enumerate(case["gen"]):
                        p = opf["gen_p_mw"][mpc.gen_id(i)]
                        self.assertGreaterEqual(p, gen[mpc.PMIN] - 1e-5)
                        self.assertLessEqual(p, gen[mpc.PMAX] + 1e-5)
                        scheduled[mpc.bus_id(gen[mpc.GEN_BUS])] += p
                        gc = case["gencost"][i]
                        objective += float(np.polyval(gc[4 : 4 + int(gc[3])], p))
                    for bus in case["bus"]:
                        k = mpc.bus_id(bus[mpc.BUS_I])
                        self.assertAlmostEqual(
                            kcl[k], scheduled[k] - bus[mpc.PD] - bus[mpc.GS], delta=1e-5
                        )
                    for i, br in enumerate(case["branch"]):
                        if br[mpc.RATE_A] > 0:
                            self.assertLessEqual(
                                abs(opf["branch_flow_mw"][mpc.branch_id(i)]),
                                br[mpc.RATE_A] + 1e-5,
                            )
                    self.assertAlmostEqual(opf["objective"], objective, delta=1e-5)

    def test_ac_losses_include_every_branch_and_match_slack_uplift(self):
        for nid, case, pp, _ in self.records():
            with self.subTest(case=nid):
                ac = pp["ac"]
                self.assertTrue(ac["converged"])
                nodal = self.nodal_branch_injections(
                    case, ac["branch_flow_mw"], ac["branch_flow_to_mw"]
                )
                for bid, p in nodal.items():
                    self.assertAlmostEqual(p, ac["bus_injection_mw"][bid], delta=1e-5)
                self.assertGreater(ac["total_losses_mw"], 0)
                self.assertAlmostEqual(sum(nodal.values()), ac["total_losses_mw"], delta=1e-6)
                self.assertAlmostEqual(
                    ac["ext_grid_p_mw"] - pp["dispatch"]["slack_gen_p_mw"],
                    ac["total_losses_mw"],
                    delta=1e-5,
                )

    def test_artifact_envelopes_index_and_current_input_hashes(self):
        index = mpc.read_json(compare.ARTIFACT_DIR / "index.json")
        entries = {e["artifact_id"]: e for e in index["artifacts"]}
        self.assertEqual(len(entries), len(index["artifacts"]))
        for nid in CASE_IDS:
            with self.subTest(case=nid):
                aid = f"cross-engine-{nid}"
                path = compare.ARTIFACT_DIR / f"{aid}.json"
                self.assertLess(path.stat().st_size, 5 * 1024 * 1024)
                art = json.loads(path.read_text("utf-8"))
                header, payload = art["artifact"], art["payload"]
                self.assertEqual(header["schema_version"], "gridstorm-artifact/1.0")
                self.assertEqual(header["kind"], "benchmark")
                self.assertEqual(header["network_id"], nid)
                self.assertEqual(header["artifact_id"], aid)
                self.assertEqual(header["execution_mode"], "precomputed")
                self.assertEqual(header["payload_sha256"], compare.canonical_sha256(payload))
                self.assertEqual(entries[aid]["payload_sha256"], header["payload_sha256"])
                for source in header["inputs"]:
                    self.assertEqual(
                        mpc.sha256_file(mpc.REPO / Path(source["path"])), source["sha256"]
                    )
                self.assertEqual(payload["summary"]["DISAGREES"], 0)
                self.assertEqual(payload["summary"]["NOT_RUN"], 0)
                self.assertEqual(payload["conversion"]["pypsa_mapping_issues"], [])


if __name__ == "__main__":
    CASE_IDS = sys.argv[1:] or list(mpc.CASES)
    unittest.main(argv=[sys.argv[0]], verbosity=2)
