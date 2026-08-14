"""Command-line entry point for local Releaseforge workflows."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from releaseforge.compare import (
    ComparisonError,
    compare_packets,
    comparison_payload,
    load_packet,
    render_comparison_text,
)
from releaseforge.config import ConfigError, load_plan
from releaseforge.demo import DemoError, create_demo
from releaseforge.evaluate import evaluate_release
from releaseforge.inspect import InspectionError, inspect_release
from releaseforge.report import Report, ReportError, make_report, report_payload, write_packet

INIT_TEMPLATE = """# This is a workflow declaration, not a distributor-compliance promise.
# Replace every placeholder and verify the requirements against the real destination.

[release]
title = "Untitled release"
artist = "Primary artist"
catalogue_number = "CAT-001"
planned_release_date = "2026-09-01"

[requirements]
minimum_cover_pixels = 3000
require_square_cover = true
allowed_audio_extensions = [".wav", ".flac", ".aiff"]

[assets]
cover = "artwork/final-cover.jpg"

[declarations]
rights_review = "declared_pending"
metadata_review = "declared_pending"
artwork_approval = "declared_pending"

[[tracks]]
number = 1
title = "Track title"
file = "audio/01-track-title.wav"
declared_master_status = "declared_pending"
"""


def main(argv: Sequence[str] | None = None) -> int:
    """Run Releaseforge and return 0, 1, or 2 without raising for normal input errors."""
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command == "init":
        return _init(Path(args.release_dir))
    if args.command == "demo":
        return _demo(Path(args.destination))
    if args.command == "compare":
        return _compare(Path(args.before), Path(args.after), as_json=args.as_json)

    try:
        report = _load_report(Path(args.release_dir))
    except (ConfigError, InspectionError) as error:
        _error(str(error))
        return 2

    if args.command == "check":
        _print_summary(report)
        print("No packet was written.")
        return _evaluation_exit_code(report)
    if args.command == "build":
        try:
            packet = write_packet(report, Path(args.output))
        except ReportError as error:
            _error(str(error))
            return 2
        _print_summary(report)
        print(f"Wrote release proof packet: {packet.name}")
        return _evaluation_exit_code(report)
    parser.error(f"unsupported command: {args.command}")
    return 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="releaseforge",
        description="Generate local release proof before distributor upload.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    init_parser = commands.add_parser("init", help="create a commented release.toml template")
    init_parser.add_argument("release_dir", help="new or existing release directory")

    demo_parser = commands.add_parser(
        "demo", help="create a synthetic two-version workflow in a new directory"
    )
    demo_parser.add_argument("destination", help="new directory for synthetic demo files")

    check_parser = commands.add_parser("check", help="read local facts and print a decision")
    check_parser.add_argument("release_dir", help="directory containing release.toml")

    build_parser = commands.add_parser("build", help="write a new portable proof packet")
    build_parser.add_argument("release_dir", help="directory containing release.toml")
    build_parser.add_argument(
        "--output", "-o", required=True, help="new output directory outside source"
    )

    compare_parser = commands.add_parser(
        "compare", help="compare two local proof packets without writing"
    )
    compare_parser.add_argument("before", help="proof packet directory or RELEASE_PROOF.json")
    compare_parser.add_argument("after", help="proof packet directory or RELEASE_PROOF.json")
    compare_parser.add_argument(
        "--json", dest="as_json", action="store_true", help="print machine-readable JSON"
    )
    return parser


def _init(release_dir: Path) -> int:
    plan_path = release_dir / "release.toml"
    if plan_path.exists():
        _error("release.toml already exists; init will not replace it")
        return 2
    try:
        if release_dir.exists() and not release_dir.is_dir():
            _error("release directory path exists but is not a directory")
            return 2
        release_dir.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(INIT_TEMPLATE, encoding="utf-8")
    except OSError as error:
        _error(f"could not create release.toml: {error}")
        return 2
    print(
        "Created release.toml. Add your local paths and verify the declared workflow requirements."
    )
    return 0


def _demo(destination: Path) -> int:
    """Create a local synthetic demo without inspecting any user release material."""
    try:
        create_demo(destination)
    except DemoError as error:
        _error(str(error))
        return 2
    print("Created a synthetic local Releaseforge demo.")
    print("Open START_HERE.md in the destination, then run: releaseforge compare proof-v1 proof-v2")
    return 0


def _load_report(release_dir: Path) -> Report:
    plan = load_plan(release_dir)
    inspection = inspect_release(plan)
    return make_report(plan, inspection, evaluate_release(plan, inspection))


def _compare(before: Path, after: Path, *, as_json: bool) -> int:
    """Compare two existing packet captures without reading or writing source media."""
    try:
        comparison = compare_packets(load_packet(before), load_packet(after))
    except ComparisonError as error:
        _error(str(error))
        return 2
    if as_json:
        print(
            json.dumps(comparison_payload(comparison), ensure_ascii=False, indent=2, sort_keys=True)
        )
    else:
        print(render_comparison_text(comparison))
    return 0 if comparison.is_equal else 1


def _print_summary(report: Report) -> None:
    payload = report_payload(report)
    decision = payload["decision"]
    release = payload["release"]
    print("LOCAL RELEASE PROOF")
    print(f"Release: {release['artist']} — {release['title']} ({release['catalogue_number']})")
    print(f"Decision: {decision['state']}")
    print(
        " | ".join(
            (
                f"Blockers: {decision['blocker_count']}",
                f"Warnings: {decision['warning_count']}",
                f"Needs evidence: {decision['needs_evidence_count']}",
            )
        )
    )
    if payload["findings"]:
        for finding in payload["findings"]:
            print(f"- {finding['severity'].upper()}: {finding['message']}")
    else:
        print("- No blocker, warning, or pending-evidence findings.")


def _evaluation_exit_code(report: Report) -> int:
    return 1 if report.evaluation.blocker_count else 0


def _error(message: str) -> None:
    print(f"releaseforge: {message}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
