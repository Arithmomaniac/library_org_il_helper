from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum


class ErrorCode(StrEnum):
    HTTP = "http_error"
    NETWORK = "network_error"
    PROTOCOL = "invalid_response"
    MEMBERSHIP = "membership_unavailable"


class Outcome(StrEnum):
    RENEWED = "renewed"
    SKIPPED = "skipped"
    REJECTED = "rejected"
    UNVERIFIED = "unverified"


class Reason(StrEnum):
    PERMISSION = "permission_not_granted"
    MISSING_COPY = "missing_copy"
    MISSING_DUE = "missing_due_date"
    MISSING_CHECKOUT = "missing_checkout_date"
    RETURNED = "already_returned"
    EXTENDED = "already_extended"
    RESERVED = "reserved"
    UNKNOWN_RESERVATION = "reservation_state_unknown"
    MISSING = "loan_not_found"
    CHANGED = "checkout_changed"
    REFRESH = "refresh_failed"
    VERIFIED = "later_due_date"
    HTTP_REJECTION = "request_rejected"
    UNVERIFIED = "no_verified_extension"


@dataclass(frozen=True)
class Account:
    label: str
    tz: str = field(repr=False)
    libraries: tuple[str, ...] | None = None

    def __post_init__(self):
        if not isinstance(self.tz, str) or not self.tz.isascii() or not self.tz.isdigit():
            raise ValueError("Each account needs a numeric TZ stored as a string.")
        if (
            not isinstance(self.label, str) or not self.label.strip()
            or any(ord(c) < 32 for c in self.label)
        ):
            raise ValueError("Each account needs a nonempty alias.")
        if self.libraries is not None and (
            not isinstance(self.libraries, tuple) or not self.libraries
            or any(not isinstance(key, str) or ":" not in key for key in self.libraries)
            or len(set(self.libraries)) != len(self.libraries)
        ):
            raise ValueError("libraries must be a nonempty list of unique membership keys.")


@dataclass(frozen=True)
class Membership:
    account: Account = field(repr=False)
    server: str
    database: str = field(repr=False)
    name: str
    allow_extension: bool | None

    @property
    def key(self) -> str:
        return f"{self.server}:{self.database}"


@dataclass
class Discovery:
    memberships: list[Membership] = field(default_factory=list)
    errors: dict[str, ErrorCode] = field(default_factory=dict)


@dataclass(frozen=True)
class Loan:
    membership: Membership = field(repr=False)
    title: str
    copy_id: str | int | None
    author: str | None = None
    checkout_date: date | None = None
    due_date: date | None = None
    return_date: date | None = None
    extension_date: date | None = None
    reserved: bool | None = None

    @property
    def blocked_reason(self) -> Reason | None:
        if not self.membership.allow_extension:
            return Reason.PERMISSION
        if self.copy_id is None:
            return Reason.MISSING_COPY
        if self.due_date is None:
            return Reason.MISSING_DUE
        if self.checkout_date is None:
            return Reason.MISSING_CHECKOUT
        if self.return_date:
            return Reason.RETURNED
        if self.extension_date:
            return Reason.EXTENDED
        if self.reserved is True:
            return Reason.RESERVED
        if self.reserved is None:
            return Reason.UNKNOWN_RESERVATION
        return None


@dataclass(frozen=True)
class RenewalResult:
    loan: Loan
    outcome: Outcome
    reason: Reason
    new_due_date: date | None = None

    @property
    def success(self) -> bool:
        return self.outcome == Outcome.RENEWED
