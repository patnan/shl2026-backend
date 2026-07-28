#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

from src.shl.api import compare_game_score_change_from_files


def resolve_output_path(cache_dir: Path, path_value: str) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return cache_dir / path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare two game JSON objects and report if a team has scored"
    )
    parser.add_argument(
        "previous_file",
        help="Path to previous game JSON file",
    )
    parser.add_argument(
        "current_file",
        help="Path to current game JSON file",
    )
    parser.add_argument(
        "--output",
        help="Optional output JSON file path for the comparison result",
    )
    parser.add_argument(
        "--cache-dir",
        default="cache",
        help="Directory where generated JSON files are stored (default: cache)",
    )
    args = parser.parse_args()
    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    result = compare_game_score_change_from_files(args.previous_file, args.current_file)

    if args.output:
        output_path = resolve_output_path(cache_dir, args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Saved comparison JSON to: {output_path}")

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
