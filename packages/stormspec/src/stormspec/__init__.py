"""StormSpec — typed crisis-scenario specification for GridStorm (``stormspec/1.0``)."""

from .capabilities import CAPABILITIES, EngineCapabilities
from .eens import eens
from .hashing import (
    canonical_dumps,
    canonical_json,
    file_sha256,
    payload_sha256,
    result_sha256,
    scenario_hash,
)
from .io import PRESETS_DIR, load_presets, load_scenario, load_scenario_dict, preset_paths
from .manifest import ExecutionManifest
from .models import (
    EVENT_TYPES,
    SCHEMA_VERSION,
    Dataset,
    DemandMultiplier,
    Event,
    Execution,
    GeneratorOutage,
    Horizon,
    LineOutage,
    LinkOutage,
    LoadShedding,
    Mitigation,
    RenewableAvailabilityMultiplier,
    Scenario,
    SolverOptions,
    StorageState,
    Window,
)
from .validation import Issue, ValidationReport, check_capabilities, validate

__version__ = "1.0.0"

__all__ = [
    "CAPABILITIES",
    "EVENT_TYPES",
    "PRESETS_DIR",
    "SCHEMA_VERSION",
    "Dataset",
    "DemandMultiplier",
    "EngineCapabilities",
    "Event",
    "Execution",
    "ExecutionManifest",
    "GeneratorOutage",
    "Horizon",
    "Issue",
    "LineOutage",
    "LinkOutage",
    "LoadShedding",
    "Mitigation",
    "RenewableAvailabilityMultiplier",
    "Scenario",
    "SolverOptions",
    "StorageState",
    "ValidationReport",
    "Window",
    "canonical_dumps",
    "canonical_json",
    "check_capabilities",
    "eens",
    "file_sha256",
    "load_presets",
    "load_scenario",
    "load_scenario_dict",
    "payload_sha256",
    "preset_paths",
    "result_sha256",
    "scenario_hash",
    "validate",
]
