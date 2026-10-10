# In plain English: Validates receipt bytes and stores uploads outside the public static directory.
"""Receipt storage and validation helper.

Owner: C
Assigned branch: codex/treasury-comms

Per CONTRACT.md §1.8, §4.3 and REQUIREMENTS.md EXP-02, EXP-03.
- Allowed MIME types: image/png, image/jpeg, application/pdf
- Size: 1 to 5,242,880 bytes (5 MB)
- Magic-byte sniffing: verifies actual bytes match declared MIME type
- Safe random storage name outside static files
- Sanitized filenames against path traversal
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import secrets
from typing import Tuple

from clubledger.config import get_config
from clubledger.core.errors import DomainError


ALLOWED_MIMES = {
    "image/png": b"\x89PNG\r\n\x1a\n",
    "image/jpeg": b"\xff\xd8\xff",
    "application/pdf": b"%PDF",
}
MAX_RECEIPT_BYTES = 5 * 1024 * 1024  # 5 MB


def get_receipts_storage_dir() -> Path:
    """Resolve receipts storage directory safely."""
    override = os.environ.get("CLUBLEDGER_RECEIPTS_DIR")
    if override:
        receipts_dir = Path(override).resolve()
        receipts_dir.mkdir(parents=True, exist_ok=True)
        return receipts_dir
    config = get_config()
    data_dir = getattr(config, "data_dir", None)
    if not data_dir:
        data_dir = Path(config.db_path).resolve().parent
    receipts_dir = Path(data_dir) / "receipts"
    receipts_dir.mkdir(parents=True, exist_ok=True)
    return receipts_dir


def validate_and_save_receipt(
    content: bytes,
    original_filename: str,
    declared_mime: str,
    *,
    database_storage: bool = False,
) -> Tuple[str, str, int, str]:
    """Validate content, sniff magic bytes, and store securely.

    Returns (stored_name, sanitized_original_name, size_bytes, sha256_hex).
    Raises DomainError("UPLOAD_REJECTED", 422) on any validation failure.
    """
    size_bytes = len(content)
    limit = 3 * 1024 * 1024 if database_storage else MAX_RECEIPT_BYTES
    if size_bytes < 1 or size_bytes > limit:
        raise DomainError(
            "UPLOAD_REJECTED",
            422,
            f"Receipt size {size_bytes} out of allowed bounds (1 to {limit // (1024 * 1024)}MB)",
        )

    if declared_mime not in ALLOWED_MIMES:
        raise DomainError(
            "UPLOAD_REJECTED", 422, f"Disallowed MIME type: {declared_mime}"
        )

    # Sniff magic bytes
    expected_magic = ALLOWED_MIMES[declared_mime]
    if not content.startswith(expected_magic):
        raise DomainError(
            "UPLOAD_REJECTED",
            422,
            f"File magic bytes do not match declared MIME {declared_mime}",
        )

    # Sanitize original filename (prevent path traversal)
    safe_name = (
        Path(original_filename)
        .name.replace("..", "")
        .replace("/", "")
        .replace("\\", "")
    )
    if not safe_name:
        safe_name = "receipt.dat"

    # Compute sha256
    sha256_hex = hashlib.sha256(content).hexdigest()

    # Generate random unique stored name
    ext = ".bin"
    if declared_mime == "image/png":
        ext = ".png"
    elif declared_mime == "image/jpeg":
        ext = ".jpg"
    elif declared_mime == "application/pdf":
        ext = ".pdf"

    random_hex = secrets.token_hex(16)
    stored_name = f"{random_hex}{ext}"

    # Cloud bytes are saved by attach_receipt in the same DB transaction as metadata.
    if not database_storage:
        storage_dir = get_receipts_storage_dir()
        target_path = storage_dir / stored_name
        target_path.write_bytes(content)

    return stored_name, safe_name, size_bytes, sha256_hex


def resolve_receipt_file(stored_name: str) -> Path:
    """Resolve stored receipt path ensuring it stays inside the storage dir."""
    storage_dir = get_receipts_storage_dir().resolve()
    target = (storage_dir / Path(stored_name).name).resolve()
    if not target.is_relative_to(storage_dir):
        raise DomainError("NOT_FOUND", 404, "Invalid receipt path")
    if not target.exists() or not target.is_file():
        raise DomainError("NOT_FOUND", 404, "Receipt file not found")
    return target
