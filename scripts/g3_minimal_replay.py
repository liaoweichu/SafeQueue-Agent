#!/usr/bin/env python3
"""Run the authorized tau2-bench-only G3 minimal discrete-event replay."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.g3_replay import read_jsonl, run_tau_pilot, sha256_file, write_json


def git_revision() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, check=True, text=True
        )
    except Exception:
        return ""
    return completed.stdout.strip()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"could not parse {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def assert_frozen_inputs(config: dict[str, Any], manifest: dict[str, Any], selection: dict[str, Any]) -> None:
    frozen = config["frozen_inputs"]
    manifest_expected = frozen["event_manifest"]["selection_sha256"]
    selection_expected = frozen["g2_profiling_selection"]["selection_sha256"]
    if manifest.get("selection_sha256") != manifest_expected:
        raise ValueError("event manifest selection_sha256 does not match the G3 frozen input")
    if selection.get("selection_sha256") != selection_expected:
        raise ValueError("G2 v3 selection sha does not match the G3 frozen input")
    if selection.get("selection_contract_version") != frozen["g2_profiling_selection"][
        "selection_contract_version"
    ]:
        raise ValueError("G2 profiling selection contract version is not frozen v3")
    if selection.get("token_tercile_boundaries") != frozen["g2_profiling_selection"][
        "token_tercile_boundaries"
    ]:
        raise ValueError("G2 profiling token-tercile boundaries differ from the frozen G3 config")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=Path("experiments/configs/g3-minimal-tau-replay.json")
    )
    parser.add_argument("--event-manifest", type=Path)
    parser.add_argument("--profiling-selection", type=Path)
    parser.add_argument("--light-cache", type=Path)
    parser.add_argument("--strong-cache", type=Path)
    parser.add_argument("--light-profile", type=Path)
    parser.add_argument("--strong-profile", type=Path)
    parser.add_argument(
        "--output", type=Path, default=Path("experiments/results/g3-tau2-minimal-replay.json")
    )
    args = parser.parse_args()
    try:
        config = load_json(args.config)
        frozen = config["frozen_inputs"]
        manifest_path = args.event_manifest or Path(frozen["event_manifest"]["path"])
        selection_path = args.profiling_selection or Path(frozen["g2_profiling_selection"]["path"])
        light_cache_path = args.light_cache or Path(frozen["light_score_cache"])
        strong_cache_path = args.strong_cache or Path(frozen["strong_score_cache"])
        light_profile_path = args.light_profile or Path(frozen["light_profile"])
        strong_profile_path = args.strong_profile or Path(frozen["strong_profile"])
        required_paths = [
            args.config,
            manifest_path,
            selection_path,
            light_cache_path,
            strong_cache_path,
            light_profile_path,
            strong_profile_path,
        ]
        missing_paths = [str(path) for path in required_paths if not path.exists()]
        if missing_paths:
            raise ValueError("missing required input(s): " + ", ".join(missing_paths))
        manifest = load_json(manifest_path)
        selection = load_json(selection_path)
        assert_frozen_inputs(config, manifest, selection)
        provenance = {
            "runner_git_revision": git_revision(),
            "files": {
                str(path).replace("\\", "/"): sha256_file(path)
                for path in required_paths
                if path != args.config
            },
        }
        result = run_tau_pilot(
            manifest=manifest,
            light_cache=read_jsonl(light_cache_path),
            strong_cache=read_jsonl(strong_cache_path),
            light_profile=read_jsonl(light_profile_path),
            strong_profile=read_jsonl(strong_profile_path),
            config=config,
            input_provenance=provenance,
        )
        write_json(args.output, result)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {args.output}")
    print(f"Gate status: {result['gate']['status']}")
    print("F5 matched-danger:", result["gate"]["F5_matched_danger"]["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
