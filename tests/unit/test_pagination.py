"""Tests for pagination helpers."""

import msgspec

from hawkapi.pagination import CursorPage, CursorParams, Page, PaginationParams


class Item(msgspec.Struct):
    id: int
    name: str


class TestPaginationParams:
    def test_defaults(self):
        p = PaginationParams()
        assert p.page == 1
        assert p.size == 50

    def test_offset_and_limit(self):
        p = PaginationParams(page=3, size=20)
        assert p.offset == 40
        assert p.limit == 20

    def test_size_clamped_to_max(self):
        p = PaginationParams(size=200, max_size=100)
        assert p.limit == 100

    def test_page_minimum_is_1(self):
        p = PaginationParams(page=0)
        assert p.page == 1
        assert p.offset == 0


class TestPage:
    def test_basic_page(self):
        items = [Item(id=1, name="a"), Item(id=2, name="b")]
        page = Page(items=items, total=10, page=1, size=2)
        assert page.pages == 5
        assert len(page.items) == 2

    def test_pages_rounds_up(self):
        page = Page[Item](items=[], total=11, page=1, size=5)
        assert page.pages == 3

    def test_zero_total(self):
        page = Page[Item](items=[], total=0, page=1, size=10)
        assert page.pages == 0

    def test_serializable(self):
        page = Page(items=[Item(id=1, name="x")], total=1, page=1, size=10)
        data = msgspec.json.encode(page)
        assert b'"total":1' in data
        assert b'"pages":' in data


class TestCursorParams:
    def test_defaults(self):
        c = CursorParams()
        assert c.after is None
        assert c.limit == 50

    def test_limit_clamped(self):
        c = CursorParams(limit=500, max_limit=100)
        assert c.limit == 100


class TestCursorPage:
    def test_has_more_with_cursor(self):
        page = CursorPage(items=[Item(id=1, name="a")], next_cursor="abc")
        assert page.has_more is True

    def test_no_more_without_cursor(self):
        page = CursorPage[Item](items=[], next_cursor=None)
        assert page.has_more is False

    def test_serializable(self):
        page = CursorPage(items=[Item(id=1, name="x")], next_cursor="cur123")
        data = msgspec.json.encode(page)
        assert b'"next_cursor":"cur123"' in data
        assert b'"has_more":true' in data
