"""Reproduce GridStorm's precomputed Grid2Op episode artifacts.

Usage (from workers/grid2op):

    uv run python scripts/run_experiments.py                 # all episodes + determinism check
    uv run python scripts/run_experiments.py --max-steps 288 # shorter run

Writes ``data/artifacts/grid2op/<artifact_id>.json`` (contract §5, kind ``episode``) and
``data/artifacts/grid2op/index.json``. The Grid2Op dataset is downloaded by ``grid2op.make`` to
``~/data_grid2op`` (outside the repository).
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import grid2op

from gridstorm_grid2op.agents import AGENTS
from gridstorm_grid2op.env import ENV_NAME, NETWORK_ID, env_info, grid_layout, make_env
from gridstorm_grid2op.episode import ForcedLineOutage, run_episode, sha256_json

REPO = Path(__file__).resolve().parents[3]
DEFAULT_OUT = REPO / "data" / "artifacts" / "grid2op"
MAX_ARTIFACT_BYTES = 5 * 1024 * 1024


def artifact_doc(artifact_id, payload, info, command) -> dict:
    return {
        "artifact": {
            "schema_version": "gridstorm-artifact/1.0",
            "artifact_id": artifact_id,
            "kind": "episode",
            "engine": "grid2op",
            "engine_version": grid2op.__version__,
            "network_id": NETWORK_ID,
            "created_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "command": command,
            "inputs": [
                {
                    "path": info["dataset"]["url"],
                    "sha256": info["dataset"]["archive_sha256_published"],
                },
                {
                    "path": f"~/data_grid2op/{ENV_NAME} (extracted directory)",
                    "sha256": info["dataset"]["extracted_dir_sha256"],
                },
            ],
            "platform": f"{platform.system()}-{platform.release()} Python "
            f"{platform.python_version()}",
            "execution_mode": "precomputed",
            "payload_sha256": sha256_json(payload),
        },
        "payload": payload,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--backend", default="lightsim2grid", choices=["lightsim2grid", "pandapower"])
    ap.add_argument("--chronics", type=int, nargs="+", default=[0, 1])
    ap.add_argument("--agents", nargs="+", default=list(AGENTS), choices=list(AGENTS))
    ap.add_argument("--max-steps", type=int, default=2016, help="env steps per episode (5 min)")
    ap.add_argument("--seed", type=int, default=0, help="env seed and agent seed")
    ap.add_argument(
        "--crisis-line",
        default="1_3_3",
        help="Grid2Op line forcibly disconnected in the crisis variant",
    )
    ap.add_argument("--crisis-start", type=int, default=12, help="trace row of the forced outage")
    ap.add_argument(
        "--crisis-duration",
        type=int,
        default=288,
        help="steps during which reconnection is blocked",
    )
    ap.add_argument("--no-crisis", action="store_true")
    ap.add_argument("--skip-determinism", action="store_true")
    args = ap.parse_args(argv)

    command = "uv run python scripts/run_experiments.py " + " ".join(argv or sys.argv[1:])
    args.out.mkdir(parents=True, exist_ok=True)
    env = make_env(args.backend)
    info = env_info(env, args.backend)
    layout = grid_layout(env)

    variants: list[tuple[str, tuple[ForcedLineOutage, ...]]] = [("base", ())]
    if not args.no_crisis:
        outage = ForcedLineOutage(
            line=args.crisis_line,
            start_row=args.crisis_start,
            end_row=args.crisis_start + args.crisis_duration,
        )
        variants.append((f"outage-{args.crisis_line.replace('_', '-')}", (outage,)))

    index_entries = []
    for chronic in args.chronics:
        for variant, outages in variants:
            for agent in args.agents:
                artifact_id = f"case14-sandbox-c{chronic}-{variant}-{agent.replace('_', '-')}"
                t0 = time.perf_counter()
                payload = run_episode(
                    env,
                    agent,
                    chronics_id=chronic,
                    env_seed=args.seed,
                    agent_seed=args.seed,
                    max_steps=args.max_steps,
                    outages=outages,
                )
                wall = time.perf_counter() - t0
                payload["env"] = info
                payload["layout"] = layout
                doc = artifact_doc(artifact_id, payload, info, command)
                path = args.out / f"{artifact_id}.json"
                data = json.dumps(doc, separators=(",", ":"), ensure_ascii=False).encode()
                if len(data) > MAX_ARTIFACT_BYTES:
                    raise SystemExit(f"{artifact_id}: {len(data)} bytes exceeds 5 MB")
                path.write_bytes(data)
                k = payload["kpis"]
                title = f"{ENV_NAME} chronic {payload['episode']['chronics_name']} — {agent}" + (
                    "" if not outages else f" — forced outage {args.crisis_line}"
                )
                index_entries.append(
                    {
                        "artifact_id": artifact_id,
                        "kind": "episode",
                        "network_id": NETWORK_ID,
                        "title": title,
                        "agent": agent,
                        "chronics_id": chronic,
                        "chronics_name": payload["episode"]["chronics_name"],
                        "variant": variant,
                        "bytes": len(data),
                        "trace_sha256": payload["trace_sha256"],
                        "payload_sha256": doc["artifact"]["payload_sha256"],
                        "wall_time_s": round(wall, 2),
                        "kpis": {
                            key: k[key]
                            for key in (
                                "survival_steps",
                                "max_steps",
                                "survived",
                                "overload_line_steps",
                                "steps_with_overload",
                                "disconnection_events",
                                "actions_count",
                                "cumulative_reward",
                                "mean_rho",
                                "max_rho",
                                "blocked_actions",
                            )
                        },
                    }
                )
                print(
                    f"{artifact_id}: survival {k['survival_steps']}/{k['max_steps']} "
                    f"overload_line_steps {k['overload_line_steps']} actions "
                    f"{k['actions_count']} max_rho {k['max_rho']} trace "
                    f"{payload['trace_sha256'][:12]} ({wall:.1f}s, {len(data) / 1e3:.0f} kB)",
                    flush=True,
                )

    determinism = None
    if not args.skip_determinism:
        # Re-run the most decision-heavy configuration (greedy agent, crisis variant) from a
        # fresh environment and compare trace hashes.
        variant, outages = variants[-1]
        agent = "greedy_simulate" if "greedy_simulate" in args.agents else args.agents[-1]
        chronic = args.chronics[0]
        ref = next(
            e
            for e in index_entries
            if e["agent"] == agent and e["variant"] == variant and e["chronics_id"] == chronic
        )
        env2 = make_env(args.backend)
        rerun = run_episode(
            env2,
            agent,
            chronics_id=chronic,
            env_seed=args.seed,
            agent_seed=args.seed,
            max_steps=args.max_steps,
            outages=outages,
        )
        env2.close()
        determinism = {
            "artifact_id": ref["artifact_id"],
            "method": "independent re-run in a fresh environment with identical seeds, chronic "
            "and crisis; sha256 of canonical JSON of {steps, game_over}",
            "first_trace_sha256": ref["trace_sha256"],
            "rerun_trace_sha256": rerun["trace_sha256"],
            "identical": rerun["trace_sha256"] == ref["trace_sha256"],
        }
        print(f"determinism: {determinism['identical']} ({rerun['trace_sha256'][:12]})")
    env.close()

    index = {
        "schema_version": "gridstorm-artifact-index/1.0",
        "engine": "grid2op",
        "engine_version": grid2op.__version__,
        "backend": info["backend"],
        "backend_version": info["backend_version"],
        "env": ENV_NAME,
        "network_id": NETWORK_ID,
        "dataset": info["dataset"],
        "command": command,
        "settings": {
            "max_steps": args.max_steps,
            "seed": args.seed,
            "chronics": args.chronics,
            "agents": args.agents,
            "crisis": [
                {"line": o.line, "start_row": o.start_row, "end_row": o.end_row}
                for _, outs in variants
                for o in outs
            ],
        },
        "determinism": determinism,
        "artifacts": index_entries,
    }
    (args.out / "index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    if determinism is not None and not determinism["identical"]:
        print("DETERMINISM CHECK FAILED", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
