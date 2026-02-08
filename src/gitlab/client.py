from __future__ import annotations

import urllib.parse
from dataclasses import dataclass
from typing import Any

import requests

from src.gitlab.config import gitlab_base_url, gitlab_token


class GitLabError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, payload: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


@dataclass(frozen=True)
class GitLabProject:
    id: int
    name: str
    path: str
    path_with_namespace: str
    web_url: str
    http_url_to_repo: str


class GitLabClient:
    def __init__(self, *, base_url: str, token: str, session: requests.Session | None = None) -> None:
        self._base = base_url.rstrip("/")
        self._token = token
        self._http = session or requests.Session()

    @classmethod
    def from_env(cls, *, session: requests.Session | None = None) -> GitLabClient:
        token = gitlab_token()
        if not token:
            raise GitLabError("GITLAB_TOKEN is not set")
        return cls(base_url=gitlab_base_url(), token=token, session=session)

    def _headers(self) -> dict[str, str]:
        return {"PRIVATE-TOKEN": self._token}

    def _url(self, path: str) -> str:
        return f"{self._base}/api/v4{path}"

    def _request(
        self, method: str, path: str, *, params: dict[str, Any] | None = None
    ) -> Any:
        # GitLab accepts parameters as query (GET) and as form-encoded body (POST/PUT).
        query = params if method.upper() == "GET" else None
        data = params if method.upper() in ("POST", "PUT", "PATCH") else None
        res = self._http.request(
            method,
            self._url(path),
            headers=self._headers(),
            params=query,
            data=data,
            timeout=30,
        )
        if res.status_code == 404:
            return None
        if res.status_code >= 400:
            text = res.text
            payload: Any
            try:
                payload = res.json()
            except Exception:
                payload = {"raw": text}
            raise GitLabError(
                f"GitLab API error {res.status_code} for {method} {path}",
                status_code=res.status_code,
                payload=payload,
            )
        # Be tolerant of clients/tests that don't populate `.text` even when JSON exists.
        try:
            return res.json()
        except Exception:
            return {}

    def get_group_id(self, group_path: str) -> int:
        encoded = urllib.parse.quote(group_path, safe="")
        data = self._request("GET", f"/groups/{encoded}")
        if not isinstance(data, dict) or "id" not in data:
            raise GitLabError("Unexpected GitLab group response", payload=data)
        return int(data["id"])

    def get_project_by_path(self, path_with_namespace: str) -> GitLabProject | None:
        encoded = urllib.parse.quote(path_with_namespace, safe="")
        data = self._request("GET", f"/projects/{encoded}")
        if data is None:
            return None
        return self._parse_project(data)

    def create_project(
        self,
        *,
        namespace_id: int,
        name: str,
        path: str,
        visibility: str = "internal",
    ) -> GitLabProject:
        data = self._request(
            "POST",
            "/projects",
            params={
                "namespace_id": namespace_id,
                "name": name,
                "path": path,
                "visibility": visibility,
            },
        )
        return self._parse_project(data)

    def update_project(
        self,
        project_id: int,
        *,
        name: str | None = None,
        path: str | None = None,
    ) -> GitLabProject:
        params: dict[str, Any] = {}
        if name is not None:
            params["name"] = name
        if path is not None:
            params["path"] = path
        data = self._request("PUT", f"/projects/{int(project_id)}", params=params)
        return self._parse_project(data)

    @staticmethod
    def _parse_project(data: Any) -> GitLabProject:
        if not isinstance(data, dict):
            raise GitLabError("Unexpected GitLab project response", payload=data)
        try:
            return GitLabProject(
                id=int(data["id"]),
                name=str(data.get("name") or ""),
                path=str(data.get("path") or ""),
                path_with_namespace=str(data.get("path_with_namespace") or ""),
                web_url=str(data.get("web_url") or ""),
                http_url_to_repo=str(data.get("http_url_to_repo") or ""),
            )
        except Exception as exc:
            raise GitLabError(
                "Failed to parse GitLab project payload",
                payload={"data": data, "error": str(exc)},
            ) from exc
