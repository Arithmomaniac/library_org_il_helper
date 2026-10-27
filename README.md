> Generated with GitHub Copilot; pending human review.

# Library.org.il Helper

A small Python application for library memberships, loan reports, history, and verified renewals through Agron Mobile. It uses the ID-first, then library-selection flow rather than the redesigned AgronPlus websites.

## Setup

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/). From this checkout:

```powershell
uv sync
```

Create an ignored local `accounts.json`, with one entry per ID:

```json
[
  {"label": "reader-1", "tz": "YOUR_ID_AS_A_STRING"},
  {"label": "reader-2", "tz": "ANOTHER_ID_AS_A_STRING"}
]
```

Replace the placeholders with numeric ID strings, preserving leading zeros. Labels are unique display aliases; an ID number can also be a label if desired. Passwords are not used. Keep this file private.

## Read memberships and loans

```powershell
uv run library-il memberships
uv run library-il books
uv run library-il history --limit 20
uv run library-il report --output library_report.md
```

The app queries the three mobile servers for each ID and lists its memberships. The `memberships` output includes exact keys such as `agron:database_name`. Library names are display text, not unique selectors.

Use `--account reader-1` to select an ID alias and `--library agron:database_name` to select one of its libraries. Add `"libraries": ["agron:database_name"]` to a config entry to restrict ordinary reports to those memberships. A command-line library selector skips accounts whose configured filters exclude that library; if every selected account excludes it, the command fails. Omit `libraries` to include all discovered memberships; an empty filter is invalid. The `memberships` command still lists all discovered choices. `--config another.json` can appear before or after the command.

Books sort by earliest due date; history sorts by latest return date. A Markdown report shows account/library headings and overdue status. `uv run python report.py` delegates to `report`. Report commands never renew loans.

## Preview and execute renewals

Both modes require an explicit account and library. Replace the example membership key with one from `memberships`:

```powershell
uv run library-il renew --account reader-1 --library agron:database_name --due-within 1
uv run library-il renew --account reader-1 --library agron:database_name --due-within 1 --execute
```

The first command is a preview; only `--execute` submits renewals. The default threshold is one day, including overdue loans. Loans with unknown due dates are displayed as blocked rather than silently omitted. `uv run python renew.py` delegates to the same preview-first command and requires the same selectors.

The app requires explicit membership permission and skips books that are returned, already extended, reserved, or missing required renewal state, including the checkout date. It refreshes permission and loans before submitting each selected copy once. Eligibility is conservative, not a promise of approval.

A renewal is `renewed` only when a fresh loan read shows a later due date. HTTP 200 alone is insufficient. Other outcomes are `skipped`, an HTTP-confirmed `rejected` request, or `unverified`. A timed-out POST is not retried automatically; a subsequent read may still prove it worked. Re-running an execution command is a new operation, not an exactly-once guarantee.

## Partial results and exit codes

| Code | Meaning |
|---|---|
| 0 | Complete reads/preview, no renewal candidates, or all attempted renewals verified. Skips are explained separately. |
| 1 | Invalid input, no usable result, or wholly failed/unverified renewal execution. |
| 2 | Usable but incomplete results, or mixed renewal success/failure. |

Successful data remains visible when another server/account fails. Reports mark themselves incomplete and include warnings. Generic server HTTP 500 errors cannot distinguish absent memberships from backend failures; the app does not hide them as empty results. A valid membership with no loans is a successful empty read. Command-line syntax errors use argparse's exit code 2.

## Protocol and limits

[openapi.json](openapi.json) is an **unofficial, reverse-engineered** OpenAPI 3.1 description of four observed endpoints. It is documentation, not a generated SDK or a vendor support guarantee. Sources are the mobile site's [configuration](https://agronmobile.libnet.co.il/config.js), [server calls](https://agronmobile.libnet.co.il/Scripts/Server/Server.js), [login code](https://agronmobile.libnet.co.il/Scripts/App/Login.js), and [renewal UI](https://agronmobile.libnet.co.il/Scripts/Views/TitleInfoView.js).

The API uses a custom three-part Authorization payload. The spec models it as a precomputed header, not ordinary two-field Basic authentication. Local timestamps preserve the library's displayed calendar date. Membership results bind to the responding server and returned database; redirects and response-provided hosts are not trusted for credential routing. Loan-level `idNo` is not the login identity; the app does not interpret that undocumented integer.

Reads and a single approved renewal were verified during migration. All-library support, stable error semantics, and future API availability are not established. The renewal response body remains intentionally unspecified; application success depends on read-back verification. There is no browser automation, scheduling, or pagination layer.

## Development and migration

```powershell
uv sync
uv run pytest -q
```

Tests validate the OpenAPI description and synthetic fixtures, then exercise the real HTTP wrapper and CLI using httpx.MockTransport. The normal suite never contacts a library, reads local account credentials, or renews real books. A manual read-only smoke uses the commands above; live renewal requires a deliberate execution command.

This replaces the old two-package Joomla workspace. Old `library_il_client` / `library_il_aggregator` Python APIs, slug/password configuration, and `library-il-aggregate` command are not supported. Migrate each old username to a single `{"label": "...", "tz": "..."}` entry, remove passwords, and use discovery rather than guessing slug-to-database mappings.

Implementation lives in `src/library_org_il_helper/`: the thin HTTP wrapper, small models, and command orchestration. There is no generated client or separate aggregator framework. Project license: Apache-2.0.
