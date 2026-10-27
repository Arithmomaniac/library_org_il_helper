import asyncio
import base64
from datetime import datetime

import httpx

from .models import (
    Account, Discovery, ErrorCode, Loan, Membership, Outcome, Reason, RenewalResult,
)


SERVERS = {
    name: f"https://{name}.libnet.co.il:8443"
    for name in ("agron", "agron2", "agron3")
}
LOGIN = "/api/account/login"
LOANS = "/api/loans/getMyLoans"
HISTORY = "/api/loans/getMyLoansHistory"
RENEW = "/api/loans/extensionLoansByCopyNo"


class MobileError(Exception):
    def __init__(self, code: ErrorCode):
        self.code = code
        super().__init__(code.value)


def parse_date(value):
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise MobileError(ErrorCode.PROTOCOL)
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        raise MobileError(ErrorCode.PROTOCOL) from None


def parse_loan(membership: Membership, item: dict) -> Loan:
    if not isinstance(item, dict) or not isinstance(item.get("titleName"), str):
        raise MobileError(ErrorCode.PROTOCOL)
    if not item["titleName"].strip():
        raise MobileError(ErrorCode.PROTOCOL)
    copy_id = item.get("copyNo")
    if copy_id is not None and (
        type(copy_id) not in (str, int) or copy_id == "" or copy_id == 0
    ):
        raise MobileError(ErrorCode.PROTOCOL)
    reserved = item.get("isReserved")
    author = item.get("authorName")
    if reserved is not None and type(reserved) is not bool:
        raise MobileError(ErrorCode.PROTOCOL)
    if author is not None and not isinstance(author, str):
        raise MobileError(ErrorCode.PROTOCOL)
    return Loan(
        membership=membership, title=item["titleName"], copy_id=copy_id, author=author,
        checkout_date=parse_date(item.get("dateBorrowed")),
        due_date=parse_date(item.get("datePromise")),
        return_date=parse_date(item.get("dateReturn")),
        extension_date=parse_date(item.get("dateExtend")), reserved=reserved,
    )


def copy_key(value):
    return type(value), value


class MobileClient:
    def __init__(self, http: httpx.AsyncClient):
        self.http = http

    async def _request(self, method, server, account, path, *, database="", body=None):
        if server not in SERVERS:
            raise ValueError("Unknown mobile server.")
        token = base64.b64encode(
            f"{account.tz}:{account.tz}:{database}".encode("utf-8")
        ).decode("ascii")
        try:
            return await self.http.request(
                method, SERVERS[server] + path,
                headers={"Authorization": f"Basic {token}"},
                json=body, follow_redirects=False,
            )
        except httpx.HTTPError:
            raise MobileError(ErrorCode.NETWORK) from None

    @staticmethod
    def _json(response):
        if response.status_code != 200:
            raise MobileError(ErrorCode.HTTP)
        try:
            return response.json()
        except ValueError:
            raise MobileError(ErrorCode.PROTOCOL) from None

    async def _discover_server(self, account, server):
        response = await self._request("POST", server, account, LOGIN, body={"userid": account.tz})
        payload = self._json(response)
        if not isinstance(payload, list):
            raise MobileError(ErrorCode.PROTOCOL)
        memberships = []
        keys = set()
        for item in payload:
            if not isinstance(item, dict):
                raise MobileError(ErrorCode.PROTOCOL)
            database, name = item.get("dBName"), item.get("libraryName")
            permission = item.get("allowExtension")
            if (
                item.get("idNo") != account.tz
                or not isinstance(database, str) or not database.strip()
                or ":" in database or any(ord(c) < 32 for c in database)
                or not isinstance(name, str) or not name.strip()
                or (permission is not None and type(permission) is not bool)
            ):
                raise MobileError(ErrorCode.PROTOCOL)
            membership = Membership(account, server, database, name, permission)
            if membership.key in keys:
                raise MobileError(ErrorCode.PROTOCOL)
            keys.add(membership.key)
            memberships.append(membership)
        return memberships

    async def discover(self, account: Account) -> Discovery:
        async def fetch(server):
            try:
                return server, await self._discover_server(account, server), None
            except MobileError as error:
                return server, [], error.code

        result = Discovery()
        for server, memberships, error in await asyncio.gather(*(fetch(s) for s in SERVERS)):
            result.memberships.extend(memberships)
            if error:
                result.errors[server] = error
        return result

    async def _read(self, membership, path):
        response = await self._request(
            "GET", membership.server, membership.account, path, database=membership.database,
        )
        return self._json(response)

    async def loans(self, membership: Membership) -> list[Loan]:
        payload = await self._read(membership, LOANS)
        if not isinstance(payload, list) or any(not isinstance(group, dict) for group in payload):
            raise MobileError(ErrorCode.PROTOCOL)
        groups = [group for group in payload if group.get("listName") == "loans"]
        if len(groups) != 1 or not isinstance(groups[0].get("list"), list):
            raise MobileError(ErrorCode.PROTOCOL)
        loans = [parse_loan(membership, item) for item in groups[0]["list"]]
        keys = [copy_key(loan.copy_id) for loan in loans if loan.copy_id is not None]
        if len(keys) != len(set(keys)):
            raise MobileError(ErrorCode.PROTOCOL)
        return loans

    async def history(self, membership: Membership) -> list[Loan]:
        payload = await self._read(membership, HISTORY)
        if not isinstance(payload, list):
            raise MobileError(ErrorCode.PROTOCOL)
        return [parse_loan(membership, item) for item in payload]

    async def renew(self, membership: Membership, selected: list[Loan]) -> list[RenewalResult]:
        if any(
            loan.membership.account != membership.account
            or loan.membership.key != membership.key for loan in selected
        ):
            raise ValueError("Selected loans must belong to this account and membership.")
        if not selected:
            return []
        try:
            discovered = await self._discover_server(membership.account, membership.server)
            matches = [item for item in discovered if item.key == membership.key]
            if len(matches) != 1:
                raise MobileError(ErrorCode.MEMBERSHIP)
            fresh_membership = matches[0]
        except MobileError:
            return [RenewalResult(loan, Outcome.SKIPPED, Reason.REFRESH) for loan in selected]
        results = {}
        ordered = []
        for loan in selected:
            key = copy_key(loan.copy_id)
            if loan.copy_id is None:
                result = RenewalResult(loan, Outcome.SKIPPED, Reason.MISSING_COPY)
            elif key in results:
                result = results[key]
            else:
                result = await self._renew_one(fresh_membership, loan)
                results[key] = result
            ordered.append(result)
        return ordered

    async def _renew_one(self, membership, selected):
        if membership.allow_extension is not True:
            return RenewalResult(selected, Outcome.SKIPPED, Reason.PERMISSION)
        try:
            current = await self.loans(membership)
        except MobileError:
            return RenewalResult(selected, Outcome.SKIPPED, Reason.REFRESH)
        matches = [loan for loan in current if copy_key(loan.copy_id) == copy_key(selected.copy_id)]
        if not matches:
            return RenewalResult(selected, Outcome.SKIPPED, Reason.MISSING)
        baseline = matches[0]
        if baseline.checkout_date != selected.checkout_date:
            return RenewalResult(selected, Outcome.SKIPPED, Reason.CHANGED)
        if baseline.blocked_reason:
            return RenewalResult(baseline, Outcome.SKIPPED, baseline.blocked_reason)
        rejected = False
        try:
            response = await self._request(
                "POST", membership.server, membership.account, RENEW,
                database=membership.database, body=[baseline.copy_id],
            )
            rejected = response.status_code in (400, 401, 403, 404, 405, 409, 422)
        except MobileError:
            pass
        try:
            after = await self.loans(membership)
            updated = next(
                (loan for loan in after if copy_key(loan.copy_id) == copy_key(baseline.copy_id)),
                None,
            )
            if (
                updated and updated.due_date and updated.due_date > baseline.due_date
                and baseline.checkout_date is not None
                and updated.checkout_date == baseline.checkout_date
                and updated.return_date is None
            ):
                return RenewalResult(baseline, Outcome.RENEWED, Reason.VERIFIED, updated.due_date)
        except MobileError:
            pass
        return RenewalResult(
            baseline, Outcome.REJECTED if rejected else Outcome.UNVERIFIED,
            Reason.HTTP_REJECTION if rejected else Reason.UNVERIFIED,
        )
