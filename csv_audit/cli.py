"""Command-line entry point."""
from __future__ import annotations

import argparse
import sys

from .compare import compare
from .config import ConfigError, load_config
from .csvio import InputError, read_csv
from .reporting import write_reports


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare two CSV files and write auditable CSV reports."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--with-key", dest="keyed", action="store_true",
                      help="match records using KEY from .env (default)")
    mode.add_argument("--without-key", dest="keyed", action="store_false",
                      help="match exact record tuples as a multiset")
    parser.set_defaults(keyed=True)
    parser.add_argument("--limit", type=int, metavar="N",
                        help="compare at most N matched/unmatched units, after matching")
    parser.add_argument("--env-file", default=".env", help="dotenv file (default: .env)")
    args = parser.parse_args()

    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be a positive integer")
    try:
        config = load_config(args.env_file)
        if args.keyed and not config.key:
            raise ConfigError("Keyed mode requires KEY; set comma-separated column names in .env.")
        source = read_csv(config.file1, config.delimiter)
        target = read_csv(config.file2, config.delimiter)
        result = compare(source, target, args.keyed, config.key, args.limit)
        directory = write_reports(config, source, target, result, args.keyed, args.limit)
    except (ConfigError, InputError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    print(f"Reports written to: {directory}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
