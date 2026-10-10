"""Domain errors for ClubLedger per CONTRACT.md §9."""

from typing import Final

# Error codes and HTTP statuses per CONTRACT.md §9
ERROR_STATUS_MAP: Final[dict[str, int]] = {
    "AUTH_REQUIRED": 401,
    "FORBIDDEN": 403,
    "CSRF_FAILED": 403,
    "NOT_FOUND": 404,
    "VALIDATION": 422,
    "SOLD_OUT": 409,
    "INSUFFICIENT_STOCK": 409,
    "HOLD_EXPIRED": 409,
    "ALREADY_MEMBER": 409,
    "BAD_SIGNATURE": 400,
    "STALE_EVENT": 400,
    "EVENT_ID_REUSED": 409,
    "IDEMPOTENCY_CONFLICT": 422,
    "REFUND_BLOCKED": 409,
    "ALREADY_USED": 409,
    "TERM_CLOSED": 409,
    "CLOSE_BLOCKED": 409,
    "SELF_APPROVAL": 403,
    "UPLOAD_REJECTED": 422,
    "RATE_LIMITED": 429,
}


class DomainError(Exception):
    """Domain error representing an application-level failure (CONTRACT G8)."""

    def __init__(self, code: str, http_status: int | None = None, message: str | None = None):
        self.code = code
        self.http_status = http_status if http_status is not None else ERROR_STATUS_MAP.get(code, 400)
        self.message = message if message is not None else code
        super().__init__(f"{self.code} ({self.http_status}): {self.message}")


class MigrationError(Exception):
    """Base error for migration failure."""


class MigrationGapError(MigrationError):
    """Raised when an internal migration gap is detected."""


class MigrationDuplicateError(MigrationError):
    """Raised when duplicate migration numbers are detected."""


class MigrationChecksumError(MigrationError):
    """Raised when an applied migration has a modified checksum."""
