"""Tests for UploadFile async interface."""

from hawkapi.requests.form_data import UploadFile


async def test_read_all():
    f = UploadFile("test.txt", "text/plain", b"hello world")
    data = await f.read()
    assert data == b"hello world"


async def test_read_partial():
    f = UploadFile("test.txt", "text/plain", b"hello world")
    chunk1 = await f.read(5)
    assert chunk1 == b"hello"
    chunk2 = await f.read(6)
    assert chunk2 == b" world"


async def test_read_past_end():
    f = UploadFile("test.txt", "text/plain", b"hi")
    await f.read()
    data = await f.read()
    assert data == b""


async def test_seek_and_read():
    f = UploadFile("test.txt", "text/plain", b"abcdefgh")
    await f.seek(3)
    data = await f.read(3)
    assert data == b"def"


async def test_seek_to_start():
    f = UploadFile("test.txt", "text/plain", b"hello")
    await f.read()
    await f.seek(0)
    data = await f.read()
    assert data == b"hello"


async def test_close():
    f = UploadFile("test.txt", "text/plain", b"data")
    await f.close()  # Should not raise


async def test_size_property():
    f = UploadFile("test.txt", "text/plain", b"12345")
    assert f.size == 5


async def test_data_still_accessible():
    f = UploadFile("test.txt", "text/plain", b"raw")
    assert f.data == b"raw"
    # Reading should not affect .data
    await f.read()
    assert f.data == b"raw"
