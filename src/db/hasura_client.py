from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import requests


@dataclass(frozen=True)
class HasuraConfig:
    base_url: str
    admin_secret: str
    source_name: str = "default"


class HasuraError(RuntimeError):
    pass


class HasuraClient:
    def __init__(
        self, cfg: HasuraConfig, *, session: requests.Session | None = None
    ) -> None:
        self._cfg = cfg
        self._http = session or requests.Session()

    @property
    def cfg(self) -> HasuraConfig:
        return self._cfg

    def _url(self, path: str) -> str:
        return f"{self._cfg.base_url.rstrip('/')}/{path.lstrip('/')}"

    def _headers(self) -> dict[str, str]:
        return {
            "x-hasura-admin-secret": self._cfg.admin_secret,
            "content-type": "application/json",
        }

    def run_sql(
        self, sql: str, *, read_only: bool = False, _retries: int = 3
    ) -> dict[str, Any]:
        payload = {
            "type": "run_sql",
            "args": {
                "source": self._cfg.source_name,
                "sql": sql,
                "read_only": bool(read_only),
            },
        }
        for attempt in range(_retries):
            resp = self._http.post(
                self._url("/v2/query"),
                headers=self._headers(),
                json=payload,
                timeout=30,
            )
            if resp.status_code == 409 and attempt < _retries - 1:
                time.sleep(0.2 * (attempt + 1))
                continue
            if resp.status_code >= 400:
                raise HasuraError(
                    f"run_sql failed ({resp.status_code}): {resp.text}"
                )
            return resp.json()
        raise HasuraError("run_sql: retries exhausted")

    def metadata(self, payload: dict[str, Any]) -> dict[str, Any]:
        resp = self._http.post(
            self._url("/v1/metadata"), headers=self._headers(), json=payload, timeout=30
        )
        if resp.status_code >= 400:
            raise HasuraError(f"metadata failed ({resp.status_code}): {resp.text}")
        # Some metadata calls return {} or null.
        try:
            return resp.json()
        except Exception:
            return {"raw": resp.text}

    def graphql(self, payload: dict[str, Any], *, bearer_jwt: str) -> requests.Response:
        headers = {
            "authorization": f"Bearer {bearer_jwt}",
            "content-type": "application/json",
        }
        return self._http.post(
            self._url("/v1/graphql"),
            headers=headers,
            data=json.dumps(payload).encode("utf-8"),
            timeout=30,
        )
