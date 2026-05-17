from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx


@dataclass(frozen=True)
class UploadResult:
    ok: bool
    message: str


class DryRunInfomaniakUploader:
    def upload(self, audio_path: Path, metadata: dict) -> UploadResult:
        return UploadResult(
            ok=True,
            message=f"dry-run: would upload {audio_path.name} to Infomaniak AOD with metadata {metadata}",
        )


class InfomaniakMetadataClient:
    def __init__(
        self,
        url: str,
        username: str | None = None,
        password: str | None = None,
        timeout_seconds: float = 10.0,
    ):
        self.url = url
        self.username = username
        self.password = password
        self.timeout_seconds = timeout_seconds

    def update(self, data: str) -> UploadResult:
        target = _url_with_metadata(self.url, data)
        auth = (self.username, self.password) if self.username and self.password else None
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.get(target, auth=auth)
            response.raise_for_status()
        return UploadResult(ok=True, message=f"metadata updated ({response.status_code})")


class DryRunInfomaniakMetadataClient:
    def update(self, data: str) -> UploadResult:
        return UploadResult(ok=True, message=f"dry-run: would update Infomaniak metadata to {data!r}")


def _url_with_metadata(url: str, data: str) -> str:
    parsed = urlsplit(url)
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key != "data"]
    query.append(("data", data))
    return urlunsplit(parsed._replace(query=urlencode(query)))
