import argparse
import asyncio
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import httpx
from tabulate import tabulate

from .client import MobileClient, MobileError, SERVERS
from .models import Account, Outcome, Reason


def load_accounts(path: Path) -> list[Account]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        raise ValueError("Invalid configuration JSON.") from None
    if not isinstance(raw, list) or not raw:
        raise ValueError("Configuration must be a nonempty array of accounts.")
    accounts = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError("Each configuration entry must be an object.")
        if set(entry) - {"label", "tz", "libraries"}:
            raise ValueError("Use label, tz, and optional libraries; migrate old slug/password entries.")
        libraries = entry.get("libraries")
        if "libraries" in entry and not isinstance(libraries, list):
            raise ValueError("libraries must be a nonempty array of membership keys.")
        account = Account(
            label=entry.get("label"), tz=entry.get("tz"),
            libraries=tuple(libraries) if libraries is not None else None,
        )
        if account.libraries:
            for key in account.libraries:
                validate_key(key)
        accounts.append(account)
    if len({a.label for a in accounts}) != len(accounts):
        raise ValueError("Account aliases must be unique.")
    if len({a.tz for a in accounts}) != len(accounts):
        raise ValueError("Configure each TZ only once; combine its memberships.")
    return accounts


def validate_key(key):
    server, separator, database = key.partition(":")
    if (
        server not in SERVERS or not separator or not database.strip()
        or ":" in database or any(ord(c) < 32 for c in key)
    ):
        raise ValueError("Use an exact membership key from the memberships command.")


def nonnegative(value):
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("Must be nonnegative.")
    return number


def parser():
    root = argparse.ArgumentParser(description="Agron Mobile reports and verified renewals")
    root.add_argument("--config", type=Path, default=Path("accounts.json"))
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("memberships", "books", "history", "report", "renew"):
        command = commands.add_parser(name)
        command.add_argument("--config", type=Path, default=argparse.SUPPRESS)
        command.add_argument("--account", required=name == "renew", help="Configured account alias")
        command.add_argument("--library", required=name == "renew", help="Exact server:database key")
        if name in ("books", "history"):
            command.add_argument("--limit", type=nonnegative, default=0)
        if name == "report":
            command.add_argument("--output", type=Path, default=Path("library_report.md"))
        if name == "renew":
            command.add_argument("--due-within", type=nonnegative, default=1)
            command.add_argument("--execute", action="store_true", help="Submit renewals (default: preview)")
    return root


def clean(value):
    return " ".join(str(value).split())


def cell(value):
    return clean(value).replace("|", "\\|")


def print_records(records, *, history=False, limit=0):
    if history:
        records = sorted(records, key=lambda loan: (loan.return_date or date.min, loan.title), reverse=True)
    else:
        records = sorted(records, key=lambda loan: (loan.due_date or date.max, loan.title))
    if limit:
        records = records[:limit]
    if not records:
        print("No history found." if history else "No books checked out.")
        return
    print(tabulate([
        [
            clean(loan.membership.account.label), clean(loan.membership.name),
            clean(loan.title), (loan.return_date if history else loan.due_date) or "?",
        ]
        for loan in records
    ], headers=["Account", "Library", "Title", "Returned" if history else "Due"], tablefmt="github"))


def render_report(results, warnings):
    total = sum(len(records) for _, records, error in results if error is None)
    lines = [
        "# Library Books - Currently Checked Out", "",
        f"**Date:** {date.today().isoformat()}", "",
        f"**Total:** {total} books", "",
    ]
    if warnings:
        lines.extend(["**INCOMPLETE:** some discovery or read requests failed.", ""])
        lines.extend(f"- {cell(warning)}" for warning in warnings)
        lines.append("")
    for membership, records, error in results:
        lines.extend([f"## {cell(membership.account.label)} - {cell(membership.name)}", ""])
        if error:
            lines.extend([f"Read failed: {error}", ""])
            continue
        if not records:
            lines.extend(["No books checked out.", ""])
            continue
        lines.extend(["| Title | Due date | Status |", "|---|---|---|"])
        for loan in sorted(records, key=lambda item: (item.due_date or date.max, item.title)):
            status = "Unknown due date"
            if loan.due_date:
                days = (loan.due_date - date.today()).days
                status = f"{-days}d overdue" if days < 0 else "Due today" if days == 0 else f"{days}d left"
            lines.append(f"| {cell(loan.title)} | {loan.due_date or '?'} | {status} |")
        lines.append("")
    return "\n".join(lines)


async def run(args, accounts, client):
    if args.account is not None:
        accounts = [account for account in accounts if account.label == args.account]
        if not accounts:
            raise ValueError("Unknown account alias.")
    if args.library is not None:
        validate_key(args.library)
        accounts = [
            account for account in accounts
            if account.libraries is None or args.library in account.libraries
        ]
        if not accounts:
            raise ValueError("Requested membership is outside configured library filters.")
    warnings = []
    memberships = []
    discoveries = await asyncio.gather(*(client.discover(account) for account in accounts))
    for account, discovery in zip(accounts, discoveries):
        warnings.extend(
            f"{account.label}/{server}: {error}" for server, error in discovery.errors.items()
        )
        requested = (args.library,) if args.library is not None else account.libraries
        if requested and args.command != "memberships":
            found = {membership.key for membership in discovery.memberships}
            for key in requested:
                if key not in found:
                    if key.split(":", 1)[0] in discovery.errors:
                        warnings.append(f"{account.label}: requested membership could not be checked")
                    elif args.library is None or args.account is not None:
                        raise ValueError("Unknown membership filter; list memberships to select a key.")
        memberships.extend(
            membership for membership in discovery.memberships
            if (
                args.command == "memberships" and not args.library
                or requested is None or membership.key in requested
            )
        )
    for warning in warnings:
        print(f"Warning: {warning}", file=sys.stderr)
    if not memberships:
        print("No usable memberships found.", file=sys.stderr)
        return 1
    if args.command == "memberships":
        print(tabulate([
            [
                clean(m.account.label), m.key, clean(m.name),
                "yes" if m.allow_extension is True else "no" if m.allow_extension is False else "unknown",
            ] for m in memberships
        ], headers=["Account", "Membership", "Library", "Extensions"], tablefmt="github"))
        return 2 if warnings else 0
    if args.command == "renew":
        if len(memberships) != 1:
            raise ValueError("Renewal requires exactly one account and membership.")
        return await renew_command(args, memberships[0], client, bool(warnings))

    async def read(membership):
        try:
            records = await (
                client.history(membership) if args.command == "history" else client.loans(membership)
            )
            return membership, records, None
        except MobileError as error:
            return membership, [], error.code

    results = await asyncio.gather(*(read(membership) for membership in memberships))
    for membership, _, error in results:
        if error:
            warning = f"{membership.account.label}/{membership.key}: {error}"
            warnings.append(warning)
            print(f"Warning: {warning}", file=sys.stderr)
    usable = sum(error is None for _, _, error in results)
    if args.command == "report":
        args.output.write_text(render_report(results, warnings), encoding="utf-8")
        print("Report written.")
    else:
        print_records(
            [loan for _, loans, error in results if error is None for loan in loans],
            history=args.command == "history", limit=args.limit,
        )
    if not usable:
        return 1
    return 2 if warnings else 0


async def renew_command(args, membership, client, incomplete):
    try:
        cutoff = date.today() + timedelta(days=args.due_within)
    except OverflowError:
        raise ValueError("--due-within exceeds the supported date range.") from None
    try:
        loans = await client.loans(membership)
    except MobileError as error:
        print(f"Unable to read selected loans: {error.code}", file=sys.stderr)
        return 1
    selected = sorted(
        [loan for loan in loans if loan.due_date is None or loan.due_date <= cutoff],
        key=lambda loan: (loan.due_date or date.max, loan.title),
    )
    print("EXECUTE" if args.execute else "PREVIEW - no renewals submitted")
    if not selected:
        print("No loans match the due-date selection.")
        return 2 if incomplete else 0
    if not args.execute:
        print(tabulate([
            [clean(loan.title), loan.due_date or "?", loan.blocked_reason or "eligible"]
            for loan in selected
        ], headers=["Title", "Due", "Preview"], tablefmt="github"))
        return 2 if incomplete else 0
    results = await client.renew(membership, selected)
    print(tabulate([
        [clean(r.loan.title), r.outcome, r.reason, r.new_due_date or ""]
        for r in results
    ], headers=["Title", "Outcome", "Reason", "New due date"], tablefmt="github"))
    successes = sum(result.success for result in results)
    failures = sum(
        result.outcome in (Outcome.REJECTED, Outcome.UNVERIFIED) or result.reason == Reason.REFRESH
        for result in results
    )
    if failures:
        return 2 if successes else 1
    return 2 if incomplete else 0


async def async_main(argv=None, *, http=None):
    args = parser().parse_args(argv)
    try:
        accounts = load_accounts(args.config)
        if http is not None:
            return await run(args, accounts, MobileClient(http))
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as session:
            return await run(args, accounts, MobileClient(session))
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    except OSError:
        print("Error: unable to read configuration or write output.", file=sys.stderr)
        return 1


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    return asyncio.run(async_main(argv))
