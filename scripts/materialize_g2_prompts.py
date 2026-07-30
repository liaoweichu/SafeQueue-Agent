#!/usr/bin/env python3
"""Batch source-to-prompt materialization for G2 minimal falsification.

Reads the G2 event manifest, loads the frozen source archives for
tau2-bench, SafeToolBench, and AgentDojo, materializes every event,
and writes the rendered profiling records to disk.

Usage:
    python scripts/materialize_g2_prompts.py \
        --manifest data/g2-event-selection.json \
        --output data/processed/g2-materialized-records.jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.materializers import (
    AgentDojoMaterializer,
    MaterializedRecord,
    PromptRenderer,
    SafeToolBenchMaterializer,
    TauBenchMaterializer,
)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Batch materialize G2 verifier prompts from frozen sources."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("data/g2-event-selection.json"),
        help="Path to G2 event manifest JSON.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/g2-materialized-records.jsonl"),
        help="Output path for JSONL materialized records.",
    )
    parser.add_argument(
        "--output-summary",
        type=Path,
        default=Path("data/processed/g2-materialization-summary.json"),
        help="Output path for materialization summary JSON.",
    )
    parser.add_argument(
        "--tau-archive",
        type=Path,
        default=Path("data/raw/tau2-bench-v1.0.1.zip"),
        help="Path to tau2-bench archive.",
    )
    parser.add_argument(
        "--safetool-archive",
        type=Path,
        default=Path(
            "data/raw/safetoolbench-ffdef6e782b0b05f579316003f3b084b549f1366.zip"
        ),
        help="Path to SafeToolBench archive.",
    )
    parser.add_argument(
        "--agentdojo-archive",
        type=Path,
        default=Path("data/raw/agentdojo-v0.1.35.zip"),
        help="Path to AgentDojo archive.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate inputs and report counts without writing output.",
    )
    parser.add_argument(
        "--source",
        choices=["tau2-bench", "safetoolbench", "agentdojo"],
        help="Materialize only a single source (default: all three).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit to first N events per source (0 = no limit).",
    )
    args = parser.parse_args()

    # Load event manifest
    if not args.manifest.exists():
        print(f"ERROR: Manifest not found: {args.manifest}", file=sys.stderr)
        return 1
    payload = json.loads(args.manifest.read_text(encoding="utf-8"))
    events = payload["events"]
    print(f"Loaded {len(events)} events from {args.manifest}")

    # Group events by source
    tau_events = [e for e in events if e["source"] == "tau2-bench"]
    safetool_events = [e for e in events if e["source"] == "safetoolbench"]
    dojo_events = [e for e in events if e["source"] == "agentdojo"]
    print(
        f"  tau2-bench: {len(tau_events)}, "
        f"SafeToolBench: {len(safetool_events)}, "
        f"AgentDojo: {len(dojo_events)}"
    )

    # Initialize shared renderer
    renderer = PromptRenderer(
        policy_path=Path("experiments/prompts/policy-v1.txt"),
        template_path=Path("experiments/prompts/verifier-v1.txt"),
    )
    print(f"Policy SHA-256: {renderer.policy_sha256}")
    print(f"Template SHA-256: {renderer.template_sha256}")

    all_records: list[MaterializedRecord] = []
    all_errors: dict[str, list[str]] = {}
    archive_hashes: dict[str, str] = {}

    def _materialize_source(
        source_events: list[dict],
        materializer_factory,
        source_label: str,
        archive_path: Path,
    ) -> None:
        if args.source and source_label != args.source:
            return
        if not source_events:
            return
        if args.limit:
            source_events = source_events[: args.limit]

        if archive_path.exists():
            archive_hashes[source_label] = file_sha256(archive_path).upper()
        else:
            print(
                f"WARNING: Archive not found for {source_label}: {archive_path}",
                file=sys.stderr,
            )

        mat = materializer_factory(archive_path=archive_path, renderer=renderer)
        records, errors = mat.materialize_all(source_events)
        all_records.extend(records)
        if errors:
            all_errors[source_label] = errors
        print(f"  {source_label}: {len(records)} materialized, {len(errors)} errors")

    _materialize_source(tau_events, TauBenchMaterializer, "tau2-bench", args.tau_archive)
    _materialize_source(
        safetool_events, SafeToolBenchMaterializer, "safetoolbench", args.safetool_archive
    )
    _materialize_source(
        dojo_events, AgentDojoMaterializer, "agentdojo", args.agentdojo_archive
    )

    if args.dry_run:
        print(f"\nDRY RUN — {len(all_records)} records would be written.")
        if all_errors:
            print("Errors:")
            for source, errs in all_errors.items():
                for err in errs:
                    print(f"  [{source}] {err}")
        return 0

    # Write output
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        for record in all_records:
            f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
    print(f"\nWrote {len(all_records)} records to {args.output}")

    # Write summary
    summary = {
        "schema_version": "0.1",
        "manifest_sha256": payload.get("selection_sha256", ""),
        "policy_sha256": renderer.policy_sha256,
        "template_sha256": renderer.template_sha256,
        "archive_hashes": archive_hashes,
        "total_events": len(events),
        "total_materialized": len(all_records),
        "errors_by_source": {k: len(v) for k, v in all_errors.items()},
        "error_details": all_errors,
        "rendered_prompt_sha256_set": sorted(
            r.rendered_prompt_sha256 for r in all_records
        ),
    }
    args.output_summary.parent.mkdir(parents=True, exist_ok=True)
    args.output_summary.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Summary written to {args.output_summary}")

    if all_errors:
        print(f"\n{sum(len(v) for v in all_errors.values())} total errors:")
        for source, errs in all_errors.items():
            for err in errs[:5]:
                print(f"  [{source}] {err}")
            if len(errs) > 5:
                print(f"  [{source}] ... and {len(errs) - 5} more")

    return 0 if not all_errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
