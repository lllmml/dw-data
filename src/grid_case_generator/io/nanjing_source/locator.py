"""ZIP member safety and stable source row locator construction."""

import re
from urllib.parse import quote, unquote_to_bytes


_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")
_SOURCE_RECORD_REF = re.compile(
    r"zip-member:(?P<member>(?:[A-Za-z0-9._~/-]|%[0-9A-F]{2})+)"
    r"#data-row=(?P<data_row>[1-9][0-9]*)\Z"
)


class UnsafeZipMemberPath(ValueError):
    """Raised when a ZIP member path is absolute or traverses a parent."""


class SourceRecordRef(str):
    """A validated, immutable source CSV logical-record locator."""

    __slots__ = ()

    def __new__(cls, value: str) -> "SourceRecordRef":
        if not isinstance(value, str):
            raise TypeError("SourceRecordRef requires str")
        match = _SOURCE_RECORD_REF.fullmatch(value)
        if match is None:
            raise ValueError("invalid SourceRecordRef")
        encoded_member = match.group("member")
        try:
            member_path = unquote_to_bytes(encoded_member).decode("utf-8")
        except UnicodeError as error:
            raise ValueError("SourceRecordRef member must be UTF-8") from error
        validate_zip_member_path(member_path)
        if quote(member_path, safe="/-._~") != encoded_member:
            raise ValueError("SourceRecordRef member encoding is not canonical")
        return str.__new__(cls, value)

    @property
    def data_row(self) -> int:
        match = _SOURCE_RECORD_REF.fullmatch(self)
        assert match is not None
        return int(match.group("data_row"))


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


def source_record_ref(member_path: str, *, data_row: int) -> SourceRecordRef:
    validate_zip_member_path(member_path)
    if type(data_row) is not int:
        raise TypeError("data_row must be int")
    if data_row < 1:
        raise ValueError("data_row must be at least 1")

    encoded_path = quote(member_path, safe="/-._~", encoding="utf-8", errors="strict")
    return SourceRecordRef(f"zip-member:{encoded_path}#data-row={data_row}")
