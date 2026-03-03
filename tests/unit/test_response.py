"""Tests for Response and JSONResponse."""

import msgspec
import pytest

from hawkapi.responses.json_response import JSONResponse
from hawkapi.responses.response import Response


class TestResponse:
    @pytest.mark.asyncio
    async def test_basic_response(self):
        resp = Response("Hello", status_code=200)
        sent_messages = []

        async def send(message):
            sent_messages.append(message)

        await resp({}, lambda: None, send)

        assert len(sent_messages) == 2
        assert sent_messages[0]["type"] == "http.response.start"
        assert sent_messages[0]["status"] == 200
        assert sent_messages[1]["type"] == "http.response.body"
        assert sent_messages[1]["body"] == b"Hello"

    @pytest.mark.asyncio
    async def test_response_headers(self):
        resp = Response("OK", headers={"x-custom": "value"})
        sent_messages = []

        async def send(message):
            sent_messages.append(message)

        await resp({}, lambda: None, send)

        headers_dict = dict(sent_messages[0]["headers"])
        assert headers_dict[b"x-custom"] == b"value"

    @pytest.mark.asyncio
    async def test_response_content_type(self):
        resp = Response("OK", content_type="text/html")
        sent_messages = []

        async def send(message):
            sent_messages.append(message)

        await resp({}, lambda: None, send)

        headers_dict = dict(sent_messages[0]["headers"])
        assert headers_dict[b"content-type"] == b"text/html"

    @pytest.mark.asyncio
    async def test_response_bytes_content(self):
        resp = Response(b"raw bytes")
        assert resp.body == b"raw bytes"

    @pytest.mark.asyncio
    async def test_response_content_length(self):
        resp = Response("12345")
        sent_messages = []

        async def send(message):
            sent_messages.append(message)

        await resp({}, lambda: None, send)

        headers_dict = dict(sent_messages[0]["headers"])
        assert headers_dict[b"content-length"] == b"5"


class TestJSONResponse:
    @pytest.mark.asyncio
    async def test_dict_response(self):
        resp = JSONResponse({"key": "value"})
        sent_messages = []

        async def send(message):
            sent_messages.append(message)

        await resp({}, lambda: None, send)

        assert sent_messages[0]["status"] == 200
        body = sent_messages[1]["body"]
        assert msgspec.json.decode(body) == {"key": "value"}

    @pytest.mark.asyncio
    async def test_list_response(self):
        resp = JSONResponse([1, 2, 3])
        sent_messages = []

        async def send(message):
            sent_messages.append(message)

        await resp({}, lambda: None, send)

        body = sent_messages[1]["body"]
        assert msgspec.json.decode(body) == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_struct_response(self):
        class Item(msgspec.Struct):
            name: str
            price: float

        resp = JSONResponse(Item(name="Widget", price=9.99))
        sent_messages = []

        async def send(message):
            sent_messages.append(message)

        await resp({}, lambda: None, send)

        body = sent_messages[1]["body"]
        data = msgspec.json.decode(body)
        assert data == {"name": "Widget", "price": 9.99}

    @pytest.mark.asyncio
    async def test_status_code(self):
        resp = JSONResponse({"ok": True}, status_code=201)
        sent_messages = []

        async def send(message):
            sent_messages.append(message)

        await resp({}, lambda: None, send)

        assert sent_messages[0]["status"] == 201

    @pytest.mark.asyncio
    async def test_content_type_is_json(self):
        resp = JSONResponse({})
        sent_messages = []

        async def send(message):
            sent_messages.append(message)

        await resp({}, lambda: None, send)

        headers_dict = dict(sent_messages[0]["headers"])
        assert headers_dict[b"content-type"] == b"application/json"

    @pytest.mark.asyncio
    async def test_custom_headers(self):
        resp = JSONResponse({}, headers={"x-request-id": "abc123"})
        sent_messages = []

        async def send(message):
            sent_messages.append(message)

        await resp({}, lambda: None, send)

        headers_dict = dict(sent_messages[0]["headers"])
        assert headers_dict[b"x-request-id"] == b"abc123"
