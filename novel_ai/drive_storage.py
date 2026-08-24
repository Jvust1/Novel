from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx


DRIVE_API = "https://www.googleapis.com/drive/v3"
DRIVE_UPLOAD_API = "https://www.googleapis.com/upload/drive/v3"
FOLDER_MIME = "application/vnd.google-apps.folder"


class DriveStorageError(RuntimeError):
    pass


@dataclass(frozen=True)
class DriveConfig:
    access_token: str
    root_folder_id: str
    timeout: float = 60.0

    @classmethod
    def from_env(cls) -> "DriveConfig":
        import os

        token = os.getenv("NOVEL_DRIVE_ACCESS_TOKEN", "").strip()
        root = os.getenv("NOVEL_DRIVE_ROOT_FOLDER_ID", "").strip()
        if not token or not root:
            raise ValueError(
                "请设置 NOVEL_DRIVE_ACCESS_TOKEN 和 NOVEL_DRIVE_ROOT_FOLDER_ID"
            )
        return cls(
            access_token=token,
            root_folder_id=root,
            timeout=float(os.getenv("NOVEL_DRIVE_TIMEOUT", "60")),
        )


class GoogleDriveStorage:
    """Persist Markdown/JSON artifacts below the configured Novel Drive folder.

    OAuth/token acquisition stays outside this module. The access token is
    supplied at runtime and is never written to GitHub, Drive, or project data.
    """

    def __init__(self, config: DriveConfig, client: httpx.Client | None = None):
        self.config = config
        self._client = client or httpx.Client(timeout=config.timeout)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "GoogleDriveStorage":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _headers(self, content_type: str | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.config.access_token}"}
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    @staticmethod
    def _quote(value: str) -> str:
        return value.replace("\\", "\\\\").replace("'", "\\'")

    def _request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        response = self._client.request(method, url, **kwargs)
        if response.status_code >= 400:
            raise DriveStorageError(
                f"Drive API {response.status_code}: {response.text[:500]}"
            )
        if not response.content:
            return {}
        return response.json()

    def _find_child(
        self, parent_id: str, name: str, mime_type: str | None = None
    ) -> dict[str, Any] | None:
        clauses = [
            f"'{self._quote(parent_id)}' in parents",
            f"name = '{self._quote(name)}'",
            "trashed = false",
        ]
        if mime_type:
            clauses.append(f"mimeType = '{self._quote(mime_type)}'")
        data = self._request(
            "GET",
            f"{DRIVE_API}/files",
            params={
                "q": " and ".join(clauses),
                "pageSize": 10,
                "fields": "files(id,name,mimeType,webViewLink,modifiedTime,size)",
                "orderBy": "modifiedTime desc",
            },
            headers=self._headers(),
        )
        files = data.get("files", [])
        return files[0] if files else None

    def ensure_folder(self, parent_id: str, name: str) -> dict[str, Any]:
        existing = self._find_child(parent_id, name, FOLDER_MIME)
        if existing:
            return existing
        return self._request(
            "POST",
            f"{DRIVE_API}/files",
            params={"fields": "id,name,mimeType,webViewLink"},
            headers=self._headers("application/json"),
            json={"name": name, "mimeType": FOLDER_MIME, "parents": [parent_id]},
        )

    def _ensure_path(self, parts: list[str]) -> str:
        parent_id = self.config.root_folder_id
        for part in parts:
            parent_id = self.ensure_folder(parent_id, part)["id"]
        return parent_id

    def save_text(
        self,
        relative_path: str,
        content: str,
        *,
        mime_type: str = "text/markdown",
    ) -> dict[str, Any]:
        parts = [part for part in relative_path.replace("\\", "/").split("/") if part]
        if not parts:
            raise ValueError("relative_path 不能为空")
        parent_id = self._ensure_path(parts[:-1])
        name = parts[-1]
        existing = self._find_child(parent_id, name)
        if existing:
            file_id = existing["id"]
        else:
            metadata = self._request(
                "POST",
                f"{DRIVE_API}/files",
                params={"fields": "id,name,mimeType,webViewLink"},
                headers=self._headers("application/json"),
                json={"name": name, "mimeType": mime_type, "parents": [parent_id]},
            )
            file_id = metadata["id"]

        return self._request(
            "PATCH",
            f"{DRIVE_UPLOAD_API}/files/{file_id}",
            params={"uploadType": "media", "fields": "id,name,mimeType,webViewLink,modifiedTime,size"},
            headers=self._headers(mime_type),
            content=content.encode("utf-8"),
        )

    def save_json(self, relative_path: str, value: Any) -> dict[str, Any]:
        return self.save_text(
            relative_path,
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            mime_type="application/json",
        )
