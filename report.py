"""Delegate to the application's read-only Markdown report command."""

import sys

from library_org_il_helper.cli import main


if __name__ == "__main__":
    raise SystemExit(main(["report", *sys.argv[1:]]))
