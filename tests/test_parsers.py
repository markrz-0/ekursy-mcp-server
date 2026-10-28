import asyncio
import base64
import sys
import unittest
from pathlib import Path

import httpx
from fastmcp.utilities.types import File, Image


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from parsers import format_resource  # noqa: E402


class FormatResourceTests(unittest.TestCase):
    def format(self, response: httpx.Response, **kwargs):
        return asyncio.run(format_resource(response, **kwargs))

    def response(
        self,
        content: bytes = b"content",
        *,
        status_code: int = 200,
        content_type: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        response_headers = dict(headers or {})
        if content_type:
            response_headers["content-type"] = content_type
        return httpx.Response(
            status_code,
            content=content,
            headers=response_headers,
            request=httpx.Request("GET", "https://example.test/material"),
        )

    def test_pdf_is_returned_as_native_binary_resource(self):
        result = self.format(
            self.response(
                b"%PDF-1.7",
                content_type="application/pdf",
                headers={"content-disposition": 'attachment; filename="notes.pdf"'},
            )
        )

        self.assertIsInstance(result, File)
        resource = result.to_resource_content().resource
        self.assertEqual(resource.mime_type, "application/pdf")
        self.assertEqual(resource.uri, "file:///notes.pdf")
        self.assertEqual(base64.b64decode(resource.blob), b"%PDF-1.7")

    def test_docx_is_returned_as_native_binary_resource(self):
        mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        result = self.format(
            self.response(b"PK\x03\x04", content_type=mime),
            resourceId="42",
            kind="resource",
        )

        self.assertIsInstance(result, File)
        resource = result.to_resource_content().resource
        self.assertEqual(resource.mime_type, mime)
        self.assertEqual(resource.uri, "file:///resource_42.docx")
        self.assertEqual(base64.b64decode(resource.blob), b"PK\x03\x04")

    def test_text_is_returned_as_text(self):
        result = self.format(
            self.response("zażółć".encode(), content_type="text/plain; charset=utf-8")
        )
        self.assertEqual(result, "zażółć")

    def test_image_is_returned_as_image(self):
        result = self.format(
            self.response(b"image", content_type="image/png; charset=binary")
        )
        self.assertIsInstance(result, Image)

    def test_redirect_is_reported(self):
        result = self.format(
            self.response(status_code=302, headers={"location": "/next"})
        )
        self.assertEqual(result, "Resource redirects to: /next")

    def test_download_failure_is_reported(self):
        result = self.format(self.response(status_code=404))
        self.assertEqual(result, "Failed to download material")


if __name__ == "__main__":
    unittest.main()
