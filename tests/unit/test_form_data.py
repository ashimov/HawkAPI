"""Tests for multipart form data parsing."""

from hawkapi.requests.form_data import (
    FormData,
    UploadFile,
    parse_multipart,
    parse_urlencoded,
)


class TestUploadFile:
    def test_creation(self):
        f = UploadFile(filename="test.txt", content_type="text/plain", data=b"hello")
        assert f.filename == "test.txt"
        assert f.content_type == "text/plain"
        assert f.data == b"hello"

    def test_repr(self):
        f = UploadFile(filename="test.txt", content_type="text/plain", data=b"hello")
        assert "test.txt" in repr(f)
        assert "size=5" in repr(f)


class TestFormData:
    def test_get_field(self):
        fd = FormData(fields={"name": "Alice", "age": "30"})
        assert fd.get("name") == "Alice"
        assert fd.get("missing") is None
        assert fd.get("missing", "default") == "default"

    def test_getlist(self):
        fd = FormData(fields={"name": "Alice"})
        assert fd.getlist("name") == ["Alice"]
        assert fd.getlist("missing") == []

    def test_fields_property(self):
        fields = {"a": "1", "b": "2"}
        fd = FormData(fields=fields)
        assert fd.fields == fields

    def test_files_property(self):
        f = UploadFile(filename="test.txt", content_type="text/plain", data=b"data")
        fd = FormData(files={"file": f})
        assert fd.files["file"] is f

    def test_contains(self):
        f = UploadFile(filename="test.txt", content_type="text/plain", data=b"data")
        fd = FormData(fields={"name": "Alice"}, files={"doc": f})
        assert "name" in fd
        assert "doc" in fd
        assert "missing" not in fd

    def test_repr(self):
        fd = FormData(fields={"a": "1"}, files={})
        r = repr(fd)
        assert "FormData" in r
        assert "a" in r

    def test_empty_form_data(self):
        fd = FormData()
        assert fd.fields == {}
        assert fd.files == {}


class TestParseUrlencoded:
    def test_simple(self):
        body = b"name=Alice&age=30"
        fd = parse_urlencoded(body)
        assert fd.get("name") == "Alice"
        assert fd.get("age") == "30"

    def test_encoded_values(self):
        body = b"greeting=hello+world&path=%2Ffoo%2Fbar"
        fd = parse_urlencoded(body)
        assert fd.get("greeting") == "hello world"
        assert fd.get("path") == "/foo/bar"

    def test_blank_values(self):
        body = b"key=&other="
        fd = parse_urlencoded(body)
        assert fd.get("key") == ""
        assert fd.get("other") == ""

    def test_empty_body(self):
        fd = parse_urlencoded(b"")
        assert fd.fields == {}


class TestParseMultipart:
    def test_simple_fields(self):
        boundary = "----boundary"
        body = (
            b"------boundary\r\n"
            b'Content-Disposition: form-data; name="field1"\r\n'
            b"\r\n"
            b"value1\r\n"
            b"------boundary\r\n"
            b'Content-Disposition: form-data; name="field2"\r\n'
            b"\r\n"
            b"value2\r\n"
            b"------boundary--\r\n"
        )
        fd = parse_multipart(body, boundary)
        assert fd.get("field1") == "value1"
        assert fd.get("field2") == "value2"

    def test_file_upload(self):
        boundary = "----boundary"
        body = (
            b"------boundary\r\n"
            b'Content-Disposition: form-data; name="file"; filename="test.txt"\r\n'
            b"Content-Type: text/plain\r\n"
            b"\r\n"
            b"file content here\r\n"
            b"------boundary--\r\n"
        )
        fd = parse_multipart(body, boundary)
        assert "file" in fd.files
        f = fd.files["file"]
        assert f.filename == "test.txt"
        assert f.content_type == "text/plain"
        assert f.data == b"file content here"

    def test_mixed_fields_and_files(self):
        boundary = "----boundary"
        body = (
            b"------boundary\r\n"
            b'Content-Disposition: form-data; name="name"\r\n'
            b"\r\n"
            b"Alice\r\n"
            b"------boundary\r\n"
            b'Content-Disposition: form-data; name="avatar"; filename="photo.jpg"\r\n'
            b"Content-Type: image/jpeg\r\n"
            b"\r\n"
            b"\xff\xd8\xff\xe0\r\n"
            b"------boundary--\r\n"
        )
        fd = parse_multipart(body, boundary)
        assert fd.get("name") == "Alice"
        assert "avatar" in fd.files
        assert fd.files["avatar"].filename == "photo.jpg"
        assert fd.files["avatar"].content_type == "image/jpeg"

    def test_file_default_content_type(self):
        boundary = "----boundary"
        body = (
            b"------boundary\r\n"
            b'Content-Disposition: form-data; name="file"; filename="data.bin"\r\n'
            b"\r\n"
            b"\x00\x01\x02\r\n"
            b"------boundary--\r\n"
        )
        fd = parse_multipart(body, boundary)
        assert fd.files["file"].content_type == "application/octet-stream"

    def test_empty_multipart(self):
        boundary = "----boundary"
        body = b"------boundary--\r\n"
        fd = parse_multipart(body, boundary)
        assert fd.fields == {}
        assert fd.files == {}
