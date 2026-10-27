import base64
import json
import runpy
import sys
from datetime import date
from pathlib import Path

import httpx
import pytest

from library_org_il_helper.cli import async_main, load_accounts
from library_org_il_helper.client import HISTORY, LOGIN, LOANS, RENEW
from library_org_il_helper.models import Reason


@pytest.fixture
def config(tmp_path, membership_json):
    path = tmp_path / "accounts.json"
    path.write_text(json.dumps([{"label": "reader", "tz": membership_json["idNo"]}]))
    return path


def transport(membership_json, loan_json, *, partial=False, empty=False):
    writes = []
    current = dict(loan_json)

    def handle(request):
        if request.url.path == LOGIN:
            if request.url.host == "agron2.libnet.co.il" and partial:
                return httpx.Response(500)
            return httpx.Response(200, json=(
                [membership_json] if request.url.host == "agron.libnet.co.il" else []
            ))
        if request.url.path == RENEW:
            writes.append(json.loads(request.content))
            current["datePromise"] = "2099-12-31T00:00:00"
            return httpx.Response(200)
        if request.url.path == LOANS:
            return httpx.Response(200, json=[{
                "listName": "loans", "list": [] if empty else [current],
            }])
        if request.url.path == HISTORY:
            return httpx.Response(200, json=[] if empty else [current])
        pytest.fail("Unexpected endpoint")

    return httpx.MockTransport(handle), writes


@pytest.mark.asyncio
@pytest.mark.parametrize("partial,expected", [(False, 0), (True, 2)])
async def test_books_end_to_end(config, membership_json, loan_json, capsys, partial, expected):
    mock, _ = transport(membership_json, loan_json, partial=partial)
    async with httpx.AsyncClient(transport=mock) as http:
        code = await async_main(["--config", str(config), "books"], http=http)
    captured = capsys.readouterr()
    assert code == expected
    assert loan_json["titleName"] in captured.out
    assert membership_json["idNo"] not in captured.out + captured.err
    assert ("agron2" in captured.err) == partial


@pytest.mark.asyncio
async def test_valid_empty_read_succeeds(config, membership_json, loan_json, capsys):
    mock, _ = transport(membership_json, loan_json, empty=True)
    async with httpx.AsyncClient(transport=mock) as http:
        assert await async_main(["--config", str(config), "books"], http=http) == 0
    assert "No books" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_report_end_to_end(config, tmp_path, membership_json, loan_json):
    path = tmp_path / "report.md"
    mock, _ = transport(membership_json, dict(loan_json, titleName="Book | with\nlines"), partial=True)
    async with httpx.AsyncClient(transport=mock) as http:
        code = await async_main([
            "report", "--config", str(config), "--output", str(path)
        ], http=http)
    assert code == 2
    report = path.read_text(encoding="utf-8")
    assert "INCOMPLETE" in report
    assert "Book \\| with lines" in report
    assert membership_json["idNo"] not in report


@pytest.mark.asyncio
async def test_renew_defaults_to_preview(config, membership_json, loan_json, capsys):
    mock, writes = transport(membership_json, loan_json)
    async with httpx.AsyncClient(transport=mock) as http:
        code = await async_main([
            "--config", str(config), "renew", "--account", "reader",
            "--library", "agron:example",
        ], http=http)
    assert writes == []
    assert code == 0
    assert "PREVIEW" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_renew_execute_end_to_end(config, membership_json, loan_json, capsys):
    mock, writes = transport(membership_json, loan_json)
    async with httpx.AsyncClient(transport=mock) as http:
        code = await async_main([
            "--config", str(config), "renew", "--account", "reader",
            "--library", "agron:example", "--execute",
        ], http=http)
    assert writes == [[loan_json["copyNo"]]]
    assert code == 0
    assert "renewed" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_unknown_selector_cannot_write(config, membership_json, loan_json):
    mock, writes = transport(membership_json, loan_json)
    async with httpx.AsyncClient(transport=mock) as http:
        code = await async_main([
            "--config", str(config), "renew", "--account", "reader",
            "--library", "agron:absent", "--execute",
        ], http=http)
    assert code == 1
    assert writes == []


@pytest.mark.asyncio
async def test_invalid_alias_is_rejected_without_network(config):
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: pytest.fail("Invalid selector should not make requests")
    )) as http:
        assert await async_main([
            "--config", str(config), "books", "--account", "missing"
        ], http=http) == 1


@pytest.mark.parametrize("entries", [
    [{"slug": "old", "username": "000000018", "password": "old"}],
    [{"label": "reader", "tz": 18}],
    [{"label": "reader", "tz": "000000018", "libraries": []}],
    [{"label": "reader", "tz": "000000018"}] * 2,
    [{"label": "reader", "tz": "000000018"}, {"label": "reader", "tz": "000000026"}],
])
def test_invalid_config_does_not_echo_credentials(tmp_path, entries):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(entries))
    with pytest.raises(ValueError) as error:
        load_accounts(path)
    assert "000000018" not in str(error.value)


@pytest.mark.asyncio
async def test_history_preserves_calendar_dates(config, membership_json, loan_json, capsys):
    record = dict(loan_json, dateReturn="2026-10-23T00:30:00+03:00")
    mock, _ = transport(membership_json, record)
    async with httpx.AsyncClient(transport=mock) as http:
        assert await async_main(["--config", str(config), "history"], http=http) == 0
    assert date.fromisoformat(record["dateReturn"][:10]).isoformat() in capsys.readouterr().out


@pytest.mark.asyncio
async def test_read_failures_keep_other_membership_results(config, membership_json, loan_json, capsys):
    def handle(request):
        if request.url.path == LOGIN:
            return httpx.Response(200, json=(
                [membership_json, dict(membership_json, dBName="broken")]
                if request.url.host == "agron.libnet.co.il" else []
            ))
        auth = request.headers["Authorization"]
        if base64.b64decode(auth.split()[1]).decode().endswith(":broken"):
            return httpx.Response(500)
        return httpx.Response(200, json=[{"listName": "loans", "list": [loan_json]}])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        assert await async_main(["--config", str(config), "books"], http=http) == 2
    captured = capsys.readouterr()
    assert loan_json["titleName"] in captured.out
    assert "broken" in captured.err


@pytest.mark.asyncio
async def test_unknown_config_filter_fails_before_renewal(config, membership_json, loan_json):
    config.write_text(json.dumps([{
        "label": "reader", "tz": membership_json["idNo"], "libraries": ["agron:absent"],
    }]))
    mock, writes = transport(membership_json, loan_json)
    async with httpx.AsyncClient(transport=mock) as http:
        assert await async_main(["--config", str(config), "books"], http=http) == 1
    assert writes == []


@pytest.mark.asyncio
async def test_all_discovery_failures_are_not_success(config):
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(500)
    )) as http:
        assert await async_main(["--config", str(config), "books"], http=http) == 1


@pytest.mark.parametrize("script", ["report.py", "renew.py"])
def test_script_delegates_to_real_command(
    script, config, tmp_path, membership_json, loan_json, monkeypatch
):
    mock, writes = transport(membership_json, loan_json)
    original = httpx.AsyncClient
    monkeypatch.setattr(
        "library_org_il_helper.cli.httpx.AsyncClient",
        lambda **kwargs: original(transport=mock, **kwargs),
    )
    arguments = ["--config", str(config)]
    if script == "renew.py":
        arguments += ["--account", "reader", "--library", "agron:example"]
    else:
        arguments += ["--output", str(tmp_path / "report.md")]
    monkeypatch.setattr(sys, "argv", [script, *arguments])
    with pytest.raises(SystemExit) as error:
        runpy.run_path(str(Path(__file__).parents[1] / script), run_name="__main__")
    assert error.value.code == 0
    assert writes == []


@pytest.mark.asyncio
@pytest.mark.parametrize("option", ["--account", "--library"])
async def test_empty_renewal_selector_cannot_select_implicitly(
    config, membership_json, loan_json, option
):
    mock, writes = transport(membership_json, loan_json)
    arguments = {
        "--account": "reader", "--library": "agron:example",
    }
    arguments[option] = ""
    async with httpx.AsyncClient(transport=mock) as http:
        assert await async_main([
            "--config", str(config), "renew",
            *[value for pair in arguments.items() for value in pair], "--execute",
        ], http=http) == 1
    assert writes == []


@pytest.mark.asyncio
@pytest.mark.parametrize("threshold", [
    (date.max - date.today()).days + 1,
    1000000000,
])
async def test_unrepresentable_renewal_threshold_is_invalid_input(
    config, membership_json, loan_json, threshold
):
    mock, writes = transport(membership_json, loan_json, empty=True)
    async with httpx.AsyncClient(transport=mock) as http:
        assert await async_main([
            "--config", str(config), "renew", "--account", "reader",
            "--library", "agron:example", "--due-within", str(threshold),
        ], http=http) == 1
    assert writes == []


@pytest.mark.asyncio
async def test_largest_representable_renewal_threshold_is_valid(
    config, membership_json, loan_json
):
    mock, _ = transport(membership_json, loan_json, empty=True)
    async with httpx.AsyncClient(transport=mock) as http:
        assert await async_main([
            "--config", str(config), "renew", "--account", "reader",
            "--library", "agron:example",
            "--due-within", str((date.max - date.today()).days),
        ], http=http) == 0


@pytest.mark.asyncio
async def test_library_selection_skips_accounts_excluded_by_their_filters(
    config, membership_json, loan_json, capsys
):
    config.write_text(json.dumps([
        {"label": "reader", "tz": membership_json["idNo"], "libraries": ["agron:example"]},
        {"label": "other", "tz": "000000026", "libraries": ["agron:other"]},
    ]))
    mock, _ = transport(membership_json, loan_json)
    async with httpx.AsyncClient(transport=mock) as http:
        assert await async_main([
            "--config", str(config), "books", "--library", "agron:example",
        ], http=http) == 0
    captured = capsys.readouterr()
    assert loan_json["titleName"] in captured.out
    assert not captured.err


@pytest.mark.asyncio
async def test_library_excluded_by_all_accounts_fails_without_network(config, membership_json):
    config.write_text(json.dumps([{
        "label": "reader", "tz": membership_json["idNo"], "libraries": ["agron:other"],
    }]))
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: pytest.fail("Excluded membership must not make requests")
    )) as http:
        assert await async_main([
            "--config", str(config), "books", "--library", "agron:example",
        ], http=http) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("account,expected", [(None, 0), ("other", 1)])
async def test_global_library_selector_skips_nonmembers_but_explicit_account_is_strict(
    config, membership_json, loan_json, account, expected, capsys
):
    config.write_text(json.dumps([
        {"label": "reader", "tz": membership_json["idNo"]},
        {"label": "other", "tz": "000000026"},
    ]))

    def handle(request):
        if request.url.path == LOGIN:
            is_member = (
                json.loads(request.content)["userid"] == membership_json["idNo"]
                and request.url.host == "agron.libnet.co.il"
            )
            return httpx.Response(200, json=[membership_json] if is_member else [])
        assert request.url.path == LOANS
        return httpx.Response(200, json=[{"listName": "loans", "list": [loan_json]}])

    arguments = ["--config", str(config), "books", "--library", "agron:example"]
    if account is not None:
        arguments.extend(["--account", account])
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        assert await async_main(arguments, http=http) == expected
    if account is None:
        assert loan_json["titleName"] in capsys.readouterr().out


@pytest.mark.asyncio
async def test_missing_checkout_date_is_blocked_in_preview(
    config, membership_json, loan_json, capsys
):
    mock, writes = transport(membership_json, dict(loan_json, dateBorrowed=None))
    async with httpx.AsyncClient(transport=mock) as http:
        assert await async_main([
            "--config", str(config), "renew", "--account", "reader",
            "--library", "agron:example",
        ], http=http) == 0
    assert writes == []
    assert Reason.MISSING_CHECKOUT in capsys.readouterr().out
