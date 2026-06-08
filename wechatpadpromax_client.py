from __future__ import annotations

import base64
import json
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
                return self._validate_business_response(path, data)
            return self._validate_business_response(path, {"data": data})

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
                return self._validate_business_response(path, data)
            return self._validate_business_response(path, {"data": data})

    async def post_download(
        self,
        path: str,
        payload: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        session = await self._get_session()
        async with session.post(self._url(path, query), json=payload or {}) as resp:
            body = await resp.read()
            text = body.decode("utf-8", errors="replace")
            if resp.status >= 400:
                raise RuntimeError(f"HTTP {resp.status}: {text[:500]}")

            try:
                data = json.loads(text) if text.strip() else {}
            except Exception:
                data = None

            if isinstance(data, dict):
                return self._validate_business_response(path, data)
            if data is not None:
                return self._validate_business_response(path, {"data": data})

            content_type = resp.headers.get("Content-Type", "")
            return self._validate_business_response(
                path,
                {
                    "Base64": base64.b64encode(body).decode("ascii"),
                    "ContentType": content_type,
                },
            )

    @staticmethod
    def _validate_business_response(path: str, data: dict[str, Any]) -> dict[str, Any]:
        """Raise when WeChatPadProMAX explicitly reports a business failure."""
        for key in ("success", "Success", "ok", "OK"):
            if key in data and data[key] is False:
                message = (
                    data.get("message")
                    or data.get("Message")
                    or data.get("msg")
                    or data.get("Msg")
                    or data
                )
                raise RuntimeError(f"{path} business failure: {message}")

        for key in ("errcode", "ErrCode", "errorCode", "ErrorCode"):
            if key not in data:
                continue
            try:
                value = int(data[key])
            except Exception:
                continue
            if value != 0:
                message = data.get("errmsg") or data.get("ErrMsg") or data
                raise RuntimeError(f"{path} error {value}: {message}")

        for key in ("ret", "Ret"):
            if key not in data:
                continue
            try:
                value = int(data[key])
            except Exception:
                continue
            if value != 0:
                message = data.get("message") or data.get("Message") or data
                raise RuntimeError(f"{path} ret {value}: {message}")

        status = str(data.get("status") or data.get("Status") or "").lower()
        if status in {"error", "failed", "fail"}:
            message = data.get("message") or data.get("Message") or data
            raise RuntimeError(f"{path} status {status}: {message}")

        return data

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

    async def send_voice_base64(
        self,
        to_wxid: str,
        voice_base64: str,
        voice_type: int = 3,
        voice_time: int = 0,
    ) -> dict[str, Any]:
        payload = {
            "ToWxid": to_wxid,
            "Base64": voice_base64,
            "Type": voice_type,
            "VoiceTime": voice_time,
        }
        return await self.post_json("/Msg/SendVoice", payload)

    async def send_video_base64(
        self,
        to_wxid: str,
        video_base64: str,
        image_base64: str = "",
        play_length: int = 0,
    ) -> dict[str, Any]:
        payload = {
            "ToWxid": to_wxid,
            "Base64": video_base64,
            "ImageBase64": image_base64,
            "PlayLength": play_length,
        }
        return await self.post_json("/Msg/SendVideo", payload)

    async def share_link(
        self,
        to_wxid: str,
        xml: str,
        app_type: int = 5,
    ) -> dict[str, Any]:
        payload = {"ToWxid": to_wxid, "Type": app_type, "Xml": xml}
        return await self.post_json("/Msg/ShareLink", payload)

    async def share_location(
        self,
        to_wxid: str,
        x: float,
        y: float,
        label: str = "",
        poiname: str = "",
        scale: float = 16,
        infourl: str = "",
    ) -> dict[str, Any]:
        payload = {
            "ToWxid": to_wxid,
            "X": x,
            "Y": y,
            "Scale": scale,
            "Label": label,
            "Poiname": poiname,
            "Infourl": infourl,
        }
        return await self.post_json("/Msg/ShareLocation", payload)

    async def download_image(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.post_download("/Tools/DownloadImg", payload)

    async def download_voice(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.post_download("/Tools/DownloadVoice", payload)

    async def download_video(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.post_download("/Tools/DownloadVideo", payload)

    async def download_file(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.post_download("/Tools/DownloadFile", payload)

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
