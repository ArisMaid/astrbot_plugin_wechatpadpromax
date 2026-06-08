from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import aiohttp


class WechatPadProMaxClient:
    def __init__(
        self,
        base_url: str,
        authcode: str = "",
        timeout_seconds: int = 15,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        if not self.base_url.endswith("/api"):
            self.base_url = f"{self.base_url}/api"
        self.authcode = authcode.strip()
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self._session

    def _url(self, path: str, query: dict[str, Any] | None = None) -> str:
        normalized_path = path if path.startswith("/") else f"/{path}"
        merged_query = dict(query or {})
        if self.authcode and "authcode" not in merged_query:
            merged_query["authcode"] = self.authcode
        qs = urlencode({k: v for k, v in merged_query.items() if v is not None})
        return f"{self.base_url}{normalized_path}{'?' + qs if qs else ''}"

    async def post_json(
        self,
        path: str,
        payload: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        session = await self._get_session()
        async with session.post(self._url(path, query), json=payload or {}) as resp:
            text = await resp.text()
            try:
                data = await resp.json(content_type=None)
            except Exception:
                data = {"raw": text}
            if resp.status >= 400:
                raise RuntimeError(f"HTTP {resp.status}: {text[:500]}")
            if isinstance(data, dict):
                return data
            return {"data": data}

    async def get_json(
        self,
        path: str,
        query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        session = await self._get_session()
        async with session.get(self._url(path, query)) as resp:
            text = await resp.text()
            try:
                data = await resp.json(content_type=None)
            except Exception:
                data = {"raw": text}
            if resp.status >= 400:
                raise RuntimeError(f"HTTP {resp.status}: {text[:500]}")
            if isinstance(data, dict):
                return data
            return {"data": data}

    async def set_webhook(
        self,
        url: str,
        secret: str = "",
        message_types: list[str] | None = None,
        include_self_message: bool = False,
        retry_count: int = 3,
        timeout_seconds: int = 5,
        enabled: bool = True,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "enabled": enabled,
            "url": url,
            "secret": secret,
            "messageTypes": message_types or ["*"],
            "includeSelfMessage": include_self_message,
            "retryCount": retry_count,
            "timeout": timeout_seconds,
        }
        return await self.post_json("/Webhook/Set", payload)

    async def start_auto_sync(self) -> dict[str, Any]:
        return await self.post_json("/Msg/StartAutoSync", {})

    async def start_auto_heartbeat(self) -> dict[str, Any]:
        return await self.post_json("/Login/AutoHeartBeat", {})

    async def send_text(
        self,
        to_wxid: str,
        content: str,
        at: str = "",
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ToWxid": to_wxid,
            "Content": content,
            "Type": 1,
            "At": at,
        }
        return await self.post_json("/Msg/SendTxt", payload)

    async def send_image_base64(
        self, to_wxid: str, image_base64: str
    ) -> dict[str, Any]:
        payload = {"ToWxid": to_wxid, "Base64": image_base64}
        return await self.post_json("/Msg/UploadImg", payload)

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
