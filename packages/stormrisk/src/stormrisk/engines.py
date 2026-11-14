"""Real engine binding: the GridStorm PyPSA adapter (``gridstorm_pypsa.run_scenario``)."""

from __future__ import annotations

from pathlib import Path

from stormspec import Scenario

from .study import EngineRejected


class PypsaEngine:
    """Picklable callable ``scenario -> gridstorm-result/1.0`` backed by the PyPSA adapter.

    Adapter rejections (``ScenarioRejected``) become :class:`EngineRejected` (state classified
    ``invalid``); every other exception propagates and is classified ``error``.
    """

    def __init__(self, network_dir: str | Path) -> None:
        self.network_dir = Path(network_dir)

    def __call__(self, scenario: Scenario) -> dict:
        from gridstorm_pypsa import ScenarioRejected, run_scenario  # heavy; lazy in workers

        try:
            return run_scenario(scenario, self.network_dir)
        except ScenarioRejected as exc:
            raise EngineRejected(str(exc)) from exc

    @staticmethod
    def versions() -> dict[str, str | None]:
        from importlib.metadata import PackageNotFoundError, version

        out: dict[str, str | None] = {}
        for dist in ("pypsa", "linopy", "highspy", "gridstorm-pypsa", "stormspec", "numpy"):
            try:
                out[dist] = version(dist)
            except PackageNotFoundError:
                out[dist] = None
        return out
