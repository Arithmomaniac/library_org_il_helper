import base64
import json
from dataclasses import replace
from datetime import date

import httpx
import pytest

from library_org_il_helper.client import MobileClient, MobileError
from library_org_il_helper.models import Account, ErrorCode, Membership, Outcome, Reason


@pytest.fixture
def account(membership_json):
    return Account(label="reader", tz=membership_json["idNo"])


@pytest.fixture
def membership(account):
    return Membership(account, "agron", "example", "Example Library", True)


@pytest.mark.asyncio
async def test_discovery_preserves_partial_results_and_binds_host(account, membership_json):
    def handler(request):
        assert json.loads(request.content) == {"userid": account.tz}
        token = base64.b64decode(request.headers["Authorization"].split()[1]).decode()
        assert token == f"{account.tz}:{account.tz}:"
        if request.url.host == "agron.libnet.co.il":
            return httpx.Response(200, json=[dict(membership_json, serverUrl="https://invalid")])
        if request.url.host == "agron2.libnet.co.il":
            return httpx.Response(500)
        return httpx.Response(200, json=[])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await MobileClient(http).discover(account)
    assert [m.key for m in result.memberships] == ["agron:example"]
    assert result.errors == {"agron2": ErrorCode.HTTP}


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [{"idNo": "different"}, {"dBName": None}])
async def test_invalid_membership_is_not_success(account, membership_json, change):
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=[dict(membership_json, **change)])
    )) as http:
        result = await MobileClient(http).discover(account)
    assert not result.memberships
    assert set(result.errors.values()) == {ErrorCode.PROTOCOL}


@pytest.mark.asyncio
async def test_read_loans_selects_named_group_and_preserves_overdue_title(membership, loan_json):
    payload = [
        {"listName": "history", "list": [dict(loan_json, titleName="Historical")]},
        {"listName": "loans", "list": [loan_json]},
    ]
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=payload)
    )) as http:
        loans = await MobileClient(http).loans(membership)
    assert len(loans) == 1
    assert loans[0].title == loan_json["titleName"]
    assert loans[0].copy_id == loan_json["copyNo"]
    assert loans[0].due_date == date.fromisoformat(loan_json["datePromise"][:10])


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [[], {}, [{"listName": "history", "list": []}],
    [{"listName": "loans", "list": []}, {"listName": "loans", "list": []}]])
async def test_missing_or_ambiguous_loans_are_errors(membership, payload):
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=payload)
    )) as http:
        with pytest.raises(MobileError) as error:
            await MobileClient(http).loans(membership)
    assert error.value.code == ErrorCode.PROTOCOL


@pytest.mark.asyncio
async def test_empty_loans_and_flat_history_are_valid(membership):
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=(
            [{"listName": "loans", "list": []}] if request.url.path.endswith("getMyLoans")
            else []
        ))
    )) as http:
        client = MobileClient(http)
        assert await client.loans(membership) == []
        assert await client.history(membership) == []


@pytest.mark.asyncio
async def test_html_200_is_not_empty_data(membership):
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, text="<html>Login</html>")
    )) as http:
        with pytest.raises(MobileError) as error:
            await MobileClient(http).history(membership)
    assert error.value.code == ErrorCode.PROTOCOL


async def run_renewal(membership, membership_json, loan_json, *, change=None,
                      before=None, after=None, failure=None, status=200, duplicate=False):
    writes = []
    reads = 0

    def handler(request):
        nonlocal reads
        if request.url.path.endswith("/login"):
            return httpx.Response(200, json=[dict(membership_json, **(change or {}))])
        if request.url.path.endswith("extensionLoansByCopyNo"):
            writes.append(json.loads(request.content))
            if failure:
                raise failure("test", request=request)
            return httpx.Response(status)
        reads += 1
        if reads > 2 and after == "error":
            return httpx.Response(500)
        record = loan_json if reads <= 2 or after is None else after
        if reads == 2 and before is not None:
            record = before
        return httpx.Response(200, json=[{
            "listName": "loans", "list": [] if record == "missing" else [record],
        }])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = MobileClient(http)
        selected = await client.loans(membership)
        if duplicate:
            selected *= 2
        results = await client.renew(membership, selected)
    return results, writes


@pytest.mark.asyncio
async def test_verified_renewal_preserves_native_copy_and_deduplicates(membership, membership_json, loan_json):
    after = dict(loan_json, datePromise="2026-11-07T00:00:00", dateExtend="2026-10-26T00:00:00")
    results, writes = await run_renewal(
        membership, membership_json, loan_json, after=after, duplicate=True
    )
    assert writes == [[loan_json["copyNo"]]]
    assert all(result.outcome == Outcome.RENEWED for result in results)
    assert len(results) == 2
    assert results[0].new_due_date == date.fromisoformat(after["datePromise"][:10])


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [{"allowExtension": False}, {"allowExtension": None}])
async def test_permission_is_refreshed_before_mutation(membership, membership_json, loan_json, change):
    results, writes = await run_renewal(membership, membership_json, loan_json, change=change)
    assert writes == []
    assert results[0].reason == Reason.PERMISSION


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value,reason", [
    ("dateExtend", "2026-10-01T00:00:00", Reason.EXTENDED),
    ("dateReturn", "2026-10-01T00:00:00", Reason.RETURNED),
    ("isReserved", True, Reason.RESERVED),
    ("copyNo", None, Reason.MISSING_COPY),
    ("datePromise", None, Reason.MISSING_DUE),
])
async def test_ineligible_books_are_not_posted(membership, membership_json, loan_json, field, value, reason):
    results, writes = await run_renewal(
        membership, membership_json, dict(loan_json, **{field: value})
    )
    assert writes == []
    assert results[0].reason == reason


@pytest.mark.asyncio
@pytest.mark.parametrize("after", [None, "missing", "error"])
async def test_http_success_without_readback_proof_is_unverified(membership, membership_json, loan_json, after):
    results, writes = await run_renewal(membership, membership_json, loan_json, after=after)
    assert results[0].outcome == Outcome.UNVERIFIED


@pytest.mark.asyncio
async def test_timeout_is_not_retried_and_can_be_verified(membership, membership_json, loan_json):
    results, writes = await run_renewal(
        membership, membership_json, loan_json,
        after=dict(loan_json, datePromise="2026-11-07T00:00:00"),
        failure=httpx.ReadTimeout,
    )
    assert writes == [[loan_json["copyNo"]]]
    assert results[0].outcome == Outcome.RENEWED


@pytest.mark.asyncio
async def test_explicit_http_rejection_is_not_success(membership, membership_json, loan_json):
    results, _ = await run_renewal(membership, membership_json, loan_json, status=403)
    assert results[0].outcome == Outcome.REJECTED


@pytest.mark.asyncio
async def test_wrong_membership_is_rejected_before_network(membership, loan_json):
    from library_org_il_helper.client import parse_loan
    foreign = replace(membership, database="different")
    loan = parse_loan(foreign, loan_json)
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: pytest.fail("Unexpected network request")
    )) as http:
        with pytest.raises(ValueError):
            await MobileClient(http).renew(membership, [loan])


@pytest.mark.asyncio
async def test_different_checkout_is_not_proof_of_renewal(membership, membership_json, loan_json):
    results, _ = await run_renewal(
        membership, membership_json, loan_json,
        after=dict(
            loan_json, datePromise="2026-11-07T00:00:00",
            dateBorrowed="2026-10-26T00:00:00",
        ),
    )
    assert results[0].outcome == Outcome.UNVERIFIED


@pytest.mark.asyncio
async def test_checkout_changed_before_submission_is_not_renewed(membership, membership_json, loan_json):
    results, writes = await run_renewal(
        membership, membership_json, loan_json,
        before=dict(loan_json, dateBorrowed="2026-10-26T00:00:00"),
    )
    assert writes == []
    assert results[0].reason == Reason.CHANGED


@pytest.mark.asyncio
async def test_missing_checkout_dates_block_renewal(membership, membership_json, loan_json):
    record = dict(loan_json, dateBorrowed=None)
    results, writes = await run_renewal(
        membership, membership_json, record,
        after=dict(record, datePromise="2026-11-07T00:00:00"),
    )
    assert writes == []
    assert results[0].reason == Reason.MISSING_CHECKOUT


@pytest.mark.asyncio
async def test_missing_checkout_date_in_readback_cannot_verify_renewal(membership, membership_json, loan_json):
    results, _ = await run_renewal(
        membership, membership_json, loan_json,
        after=dict(loan_json, dateBorrowed=None, datePromise="2026-11-07T00:00:00"),
    )
    assert results[0].outcome == Outcome.UNVERIFIED


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [
    ("datePromise", "not a date"), ("dateBorrowed", 42),
    ("copyNo", True), ("titleName", None), ("isReserved", "false"),
])
async def test_malformed_records_are_errors_not_empty_results(membership, loan_json, field, value):
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=[{
            "listName": "loans", "list": [dict(loan_json, **{field: value})],
        }])
    )) as http:
        with pytest.raises(MobileError) as error:
            await MobileClient(http).loans(membership)
    assert error.value.code == ErrorCode.PROTOCOL


@pytest.mark.asyncio
async def test_loan_id_number_is_not_the_login_identity(membership, loan_json):
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=[{
            "listName": "loans", "list": [loan_json],
        }])
    )) as http:
        loans = await MobileClient(http).loans(membership)
    assert loans[0].membership == membership
    assert loans[0].title == loan_json["titleName"]


@pytest.mark.asyncio
async def test_redirects_do_not_forward_credentials(account):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(302, headers={"Location": "https://elsewhere.invalid"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True) as http:
        result = await MobileClient(http).discover(account)
    assert set(result.errors.values()) == {ErrorCode.HTTP}
    assert all(request.url.host.endswith(".libnet.co.il") for request in requests)


@pytest.mark.asyncio
async def test_repeated_library_names_are_separate_memberships(account, membership_json):
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=[membership_json])
    )) as http:
        result = await MobileClient(http).discover(account)
    assert len({membership.key for membership in result.memberships}) == 3


@pytest.mark.asyncio
async def test_mixed_inputs_preserve_per_book_results(membership, membership_json, loan_json):
    from library_org_il_helper.client import parse_loan
    selected = [
        parse_loan(membership, dict(loan_json, copyNo=None)),
        parse_loan(membership, loan_json),
    ]
    calls = []

    def handler(request):
        if request.url.path.endswith("/login"):
            return httpx.Response(200, json=[membership_json])
        if request.method == "POST":
            calls.append(json.loads(request.content))
            return httpx.Response(200)
        item = dict(loan_json, datePromise="2026-11-07T00:00:00") if calls else loan_json
        return httpx.Response(200, json=[{"listName": "loans", "list": [item]}])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        results = await MobileClient(http).renew(membership, selected)
    assert [(r.outcome, r.reason) for r in results] == [
        (Outcome.SKIPPED, Reason.MISSING_COPY), (Outcome.RENEWED, Reason.VERIFIED),
    ]
    assert [r.loan.title for r in results] == [loan.title for loan in selected]
