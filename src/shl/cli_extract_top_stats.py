import argparse
import json

from src.shl.extraction import extract_game, extract_game_by_id


class MainExecutionError(RuntimeError):
    pass



def main() -> None:
    try:
        parser = argparse.ArgumentParser(description="Extract top section stats from swehockey game events page")
        parser.add_argument(
            "url",
            nargs="?",
            default="https://stats.swehockey.se/Game/Events/1004840",
            help="Game events URL",
        )
        parser.add_argument(
            "--game-id",
            type=int,
            help="Game id (for example: 1004357). Overrides positional URL when provided.",
        )
        args = parser.parse_args()

        if args.game_id is not None:
            stats = extract_game_by_id(args.game_id)
        else:
            stats = extract_game(args.url)
        print(json.dumps(stats, indent=2, ensure_ascii=False))
    except MainExecutionError:
        raise
    except Exception as exc:
        raise MainExecutionError(f"main failed: {exc}") from exc


if __name__ == "__main__":
    main()
