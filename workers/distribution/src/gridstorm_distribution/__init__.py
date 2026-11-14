"""GridStorm distribution worker: AC time-series power flow of SimBench LV grids under stress.

See ``docs/research/simbench-distribution.md``. StormSpec scenarios are not accepted here (the
StormSpec 1.0 ``pandapower`` capability is single-snapshot); studies are driven by
:class:`StudyConfig` and ``scripts/run_studies.py``.
"""

from .study import StudyConfig, run_study, versions

__all__ = ["StudyConfig", "run_study", "versions"]
