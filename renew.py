"""Delegate to the application's preview-first renewal command."""

import sys

from library_org_il_helper.cli import main


if __name__ == "__main__":
    raise SystemExit(main(["renew", *sys.argv[1:]]))
