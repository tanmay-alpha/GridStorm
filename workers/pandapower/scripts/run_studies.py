"""Regenerate real AC reference and bounded N-1/N-2 artifacts (run from this component)."""

from __future__ import annotations

import os

# Set before NumPy/solver imports; shared hosts must not oversubscribe BLAS.
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

import argparse
import json
from pathlib import Path

from gridstorm_pandapower.model import REFERENCE_DATA, resolve_case_file
from gridstorm_pandapower.reference import reference_payload
from gridstorm_pandapower.studies import REPO_ROOT, n1_payload, wrap_artifact


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--include-case300", action="store_true")
    parser.add_argument("--output-dir", type=Path,
                        default=REPO_ROOT / "data/artifacts/pandapower")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    command = "cd workers/pandapower && uv run --locked python scripts/run_studies.py"
    if args.include_case300:
        command += " --include-case300"
    if args.output_dir.resolve() != (REPO_ROOT / "data/artifacts/pandapower").resolve():
        command += f' --output-dir "{args.output_dir.as_posix()}"'
    entries = []

    def save(artifact_id: str, kind: str, network_id: str | None, payload: dict,
             inputs: list[Path]) -> None:
        artifact = wrap_artifact(artifact_id=artifact_id, kind=kind, network_id=network_id,
                                 command=command, inputs=inputs, payload=payload)
        path = args.output_dir / f"{artifact_id}.json"
        path.write_text(json.dumps(artifact, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        entries.append({"artifact_id": artifact_id, "kind": kind, "network_id": network_id,
                        "title": payload["title"]})
        print(json.dumps({"path": str(path), "summary": payload["summary"]}), flush=True)

    reference = reference_payload()
    save("ac-reference-validation", "benchmark", None, reference,
         sorted((REFERENCE_DATA / "matpower").glob("*")))
    if not reference["summary"]["all_pass"]:
        raise RuntimeError("AC reference comparison failed; inspect ac-reference-validation.json")
    networks = ["pglib-case14-ieee", "pglib-case118-ieee"]
    if args.include_case300:
        networks.append("pglib-case300-ieee")
    for network_id in networks:
        case = resolve_case_file(network_id, REPO_ROOT / "data/networks" / network_id)
        payload = n1_payload(network_id, case, title=f"AC N-1 screening — {network_id}",
                             n2_top_k=5 if network_id == "pglib-case14-ieee" else 0)
        save(f"n1-{network_id}", "n_minus_1", network_id, payload, [case])
    (args.output_dir / "index.json").write_text(
        json.dumps({"artifacts": entries}, indent=2, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
