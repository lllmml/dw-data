"""ZIP member safety and stable source row locator construction."""

import re
from urllib.parse import quote


_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")


class UnsafeZipMemberPath(ValueError):
    """Raised when a ZIP member path is absolute or traverses a parent."""


def validate_zip_member_path(member_path: str) -> None:
    if not isinstance(member_path, str):
        raise TypeError("member_path must be str")
    if not member_path:
        raise UnsafeZipMemberPath("ZIP member path must be non-empty")
    if "\x00" in member_path:
        raise UnsafeZipMemberPath("ZIP member path must not contain NUL")
    if member_path.startswith(("/", "\\")) or _WINDOWS_DRIVE.match(member_path):
        raise UnsafeZipMemberPath(
            f"absolute ZIP member path is not allowed: {member_path!r}"
        )

    path_segments = member_path.replace("\\", "/").split("/")
    if ".." in path_segments:
        raise UnsafeZipMemberPath(
            f"parent traversal ZIP member path is not allowed: {member_path!r}"
        )


def source_record_ref(member_path: str, *, data_row: int) -> str:
    validate_zip_member_path(member_path)
    if type(data_row) is not int:
        raise TypeError("data_row must be int")
    if data_row < 1:
        raise ValueError("data_row must be at least 1")

    encoded_path = quote(member_path, safe="/-._~", encoding="utf-8", errors="strict")
    return f"zip-member:{encoded_path}#data-row={data_row}"
