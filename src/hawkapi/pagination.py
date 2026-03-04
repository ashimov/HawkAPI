"""Pagination helpers — Page[T], CursorPage[T], PaginationParams, CursorParams."""

import math

import msgspec
from msgspec.structs import force_setattr


class PaginationParams(msgspec.Struct, frozen=True):
    """Offset-based pagination parameters (injected from query string).

    Attributes:
        page: Current page number (minimum 1).
        size: Requested page size.
        max_size: Upper bound for page size (clamped automatically).
    """

    page: int = 1
    size: int = 50
    max_size: int = 100

    def __post_init__(self) -> None:
        if self.page < 1:
            force_setattr(self, "page", 1)

    @property
    def offset(self) -> int:
        """Compute the SQL OFFSET value."""
        return (self.page - 1) * self.limit

    @property
    def limit(self) -> int:
        """Compute the SQL LIMIT value (clamped to max_size)."""
        return min(self.size, self.max_size)


class CursorParams(msgspec.Struct, frozen=True):
    """Cursor-based pagination parameters (injected from query string).

    Attributes:
        after: Opaque cursor pointing to the last seen item.
        limit: Maximum number of items to return.
        max_limit: Upper bound for limit (clamped automatically).
    """

    after: str | None = None
    limit: int = 50
    max_limit: int = 100

    def __post_init__(self) -> None:
        if self.limit > self.max_limit:
            force_setattr(self, "limit", self.max_limit)


class Page[T](msgspec.Struct):
    """Offset-paginated response wrapper."""

    items: list[T]
    total: int
    page: int
    size: int
    pages: int = 0

    def __post_init__(self) -> None:
        if self.total == 0 or self.size <= 0:
            force_setattr(self, "pages", 0)
        else:
            force_setattr(self, "pages", math.ceil(self.total / self.size))


class CursorPage[T](msgspec.Struct):
    """Cursor-paginated response wrapper."""

    items: list[T]
    next_cursor: str | None = None
    has_more: bool = False

    def __post_init__(self) -> None:
        force_setattr(self, "has_more", self.next_cursor is not None)
