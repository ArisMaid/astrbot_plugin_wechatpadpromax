from __future__ import annotations

import base64
import wave
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from astrbot.api import logger
from astrbot.api.event import MessageChain
from astrbot.api.message_components import (
    At,
    AtAll,
    File,
    Forward,
    Image,
    Json,
    Location,
    Music,
    Node,
    Nodes,
    Plain,
    Record,
    Reply,
    Share,
    Video,
)

from .wechatpadpromax_client import WechatPadProMaxClient

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
VOICE_EXTENSIONS = {
    ".amr": 0,
    ".speex": 1,
    ".spx": 1,
    ".mp3": 2,
    ".wav": 3,
    ".wave": 3,
    ".silk": 4,
}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}


class WechatPadProMaxMessageSender:
    def __init__(
        self,
        client: WechatPadProMaxClient,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.client = client
        self.config = config or {}
        self.unsupported_fallback = bool(
            self.config.get("unsupported_component_fallback", True)
        )
        self.forward_max_chars = int(
            self.config.get("forward_fallback_max_chars") or 4000
        )

    async def send_chain(self, target: str, message_chain: MessageChain) -> int:
        text_parts: list[str] = []
        at_targets: list[str] = []
        sent_count = 0

        async def flush_text() -> None:
            nonlocal sent_count
            text = "".join(text_parts)
            if text.strip():
                await self.client.send_text(target, text, at=",".join(at_targets))
                sent_count += 1
            text_parts.clear()
            at_targets.clear()

        for comp in message_chain.chain:
            if isinstance(comp, Plain):
                text_parts.append(comp.text)
                continue

            if isinstance(comp, AtAll):
                at_targets.append("notify@all")
                text_parts.append("@所有人")
                continue

            if isinstance(comp, At):
                target_id = str(comp.qq).strip()
                if target_id and target_id != "all":
                    at_targets.append(target_id)
                label = comp.name or target_id
                if label:
                    text_parts.append(f"@{label}")
                continue

            if isinstance(comp, Reply):
                continue

            await flush_text()

            if isinstance(comp, Image):
                await self._send_image(target, comp)
                sent_count += 1
            elif isinstance(comp, Record):
                await self._send_record(target, comp)
                sent_count += 1
            elif isinstance(comp, Video):
                await self._send_video(target, comp)
                sent_count += 1
            elif isinstance(comp, File):
                sent_count += await self._send_file(target, comp)
            elif isinstance(comp, Node | Nodes):
                sent_count += await self._send_nodes_fallback(target, comp)
            elif isinstance(comp, Share):
                await self._send_share(target, comp)
                sent_count += 1
            elif isinstance(comp, Location):
                await self._send_location(target, comp)
                sent_count += 1
            elif isinstance(comp, Forward):
                sent_count += await self._send_unsupported(
                    target,
                    f"[forward:{comp.id}]",
                    "Forward",
                )
            elif isinstance(comp, Json):
                sent_count += await self._send_unsupported(
                    target,
                    self._json_fallback(comp),
                    "Json",
                )
            elif isinstance(comp, Music):
                sent_count += await self._send_unsupported(
                    target,
                    self._music_fallback(comp),
                    "Music",
                )
            else:
                sent_count += await self._send_unsupported(
                    target,
                    f"[{comp.__class__.__name__}]",
                    comp.__class__.__name__,
                )

        await flush_text()
        return sent_count

    async def _send_image(self, target: str, image: Image) -> None:
        image_base64 = await image.convert_to_base64()
        await self.client.send_image_base64(target, image_base64)

    async def _send_record(self, target: str, record: Record) -> None:
        path = await record.convert_to_file_path()
        voice_type = self._guess_voice_type(record, path)
        voice_time = self._voice_duration_ms(path)
        voice_base64 = self._file_to_base64(path)
        await self.client.send_voice_base64(
            target,
            voice_base64,
            voice_type=voice_type,
            voice_time=voice_time,
        )

    async def _send_video(self, target: str, video: Video) -> None:
        path = await video.convert_to_file_path()
        video_base64 = self._file_to_base64(path)
        cover_base64 = await self._cover_to_base64(video.cover)
        play_length = self._video_play_length(video, path)
        await self.client.send_video_base64(
            target,
            video_base64,
            image_base64=cover_base64,
            play_length=play_length,
        )

    async def _send_file(self, target: str, file: File) -> int:
        source = await file.get_file(allow_return_url=True)
        name = file.name or self._basename(source) or "file"
        if not source:
            return await self._send_unsupported(target, f"[file:{name}]", "File")

        suffix = self._suffix(name, source)

        if suffix in IMAGE_EXTENSIONS:
            image = (
                Image.fromURL(source)
                if source.startswith("http")
                else Image.fromFileSystem(source)
            )
            await self._send_image(target, image)
            return 1

        if suffix in VOICE_EXTENSIONS:
            record = (
                Record.fromURL(source)
                if source.startswith("http")
                else Record.fromFileSystem(source)
            )
            await self._send_record(target, record)
            return 1

        if suffix in VIDEO_EXTENSIONS:
            video = (
                Video.fromURL(source)
                if source.startswith("http")
                else Video.fromFileSystem(source)
            )
            await self._send_video(target, video)
            return 1

        return await self._send_unsupported(target, f"[file:{name}]", "File")

    async def _send_nodes_fallback(self, target: str, comp: Node | Nodes) -> int:
        text = self._nodes_to_text(comp)
        if self.forward_max_chars > 0 and len(text) > self.forward_max_chars:
            text = text[: self.forward_max_chars] + "\n...[truncated]"
        return await self._send_unsupported(target, text, "Node/Nodes")

    async def _send_share(self, target: str, share: Share) -> None:
        xml = self._share_xml(share)
        await self.client.share_link(target, xml, app_type=5)

    async def _send_location(self, target: str, location: Location) -> None:
        label = location.content or location.title or ""
        poiname = location.title or label
        await self.client.share_location(
            target,
            x=float(location.lon),
            y=float(location.lat),
            label=label,
            poiname=poiname,
        )

    async def _send_unsupported(
        self,
        target: str,
        fallback_text: str,
        component_name: str,
    ) -> int:
        logger.warning(
            "[WeChatPadProMAX] unsupported component fallback: %s",
            component_name,
        )
        if not self.unsupported_fallback or not fallback_text.strip():
            return 0
        await self.client.send_text(target, fallback_text)
        return 1

    @staticmethod
    def _file_to_base64(path: str) -> str:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("ascii")

    @staticmethod
    def _cover_to_image(cover: str) -> Image | None:
        cover = str(cover or "").strip()
        if not cover:
            return None
        if cover.startswith("base64://"):
            return Image.fromBase64(cover.removeprefix("base64://"))
        if cover.startswith("http://") or cover.startswith("https://"):
            return Image.fromURL(cover)
        if Path(cover).exists():
            return Image.fromFileSystem(cover)
        return None

    async def _cover_to_base64(self, cover: str | None) -> str:
        image = self._cover_to_image(cover or "")
        if not image:
            return ""
        try:
            return await image.convert_to_base64()
        except Exception as e:
            logger.warning("[WeChatPadProMAX] video cover conversion failed: %s", e)
            return ""

    @staticmethod
    def _voice_duration_ms(path: str) -> int:
        try:
            with wave.open(path, "rb") as wav:
                frames = wav.getnframes()
                rate = wav.getframerate()
                if rate > 0:
                    return int(frames / float(rate) * 1000)
        except Exception:
            return 0
        return 0

    @staticmethod
    def _video_play_length(video: Video, path: str) -> int:
        for value in (
            getattr(video, "play_length", None),
            getattr(video, "duration", None),
            getattr(video, "length", None),
        ):
            try:
                if value:
                    return int(value)
            except Exception:
                continue
        return 0 if path else 0

    @staticmethod
    def _guess_voice_type(record: Record, path: str) -> int:
        candidates = [
            getattr(record, "file", ""),
            getattr(record, "url", ""),
            getattr(record, "path", ""),
            path,
        ]
        for candidate in candidates:
            suffix = Path(str(candidate).split("?", 1)[0]).suffix.lower()
            if suffix in VOICE_EXTENSIONS:
                return VOICE_EXTENSIONS[suffix]
        return 3

    @staticmethod
    def _suffix(*values: str) -> str:
        for value in values:
            suffix = Path(str(value).split("?", 1)[0]).suffix.lower()
            if suffix:
                return suffix
        return ""

    @staticmethod
    def _basename(value: str) -> str:
        if not value:
            return ""
        return Path(str(value).split("?", 1)[0]).name

    def _nodes_to_text(self, comp: Node | Nodes) -> str:
        nodes = [comp] if isinstance(comp, Node) else comp.nodes
        lines = ["[merged forward]"]
        for idx, node in enumerate(nodes, 1):
            name = node.name or node.uin or f"node-{idx}"
            body = self._components_to_text(node.content)
            lines.append(f"{idx}. {name}: {body}")
        return "\n".join(lines)

    def _components_to_text(self, components: list[Any]) -> str:
        parts: list[str] = []
        for comp in components:
            if isinstance(comp, Plain):
                parts.append(comp.text)
            elif isinstance(comp, At):
                parts.append(f"@{comp.name or comp.qq}")
            elif isinstance(comp, Image):
                parts.append("[image]")
            elif isinstance(comp, Record):
                parts.append("[voice]")
            elif isinstance(comp, Video):
                parts.append("[video]")
            elif isinstance(comp, File):
                parts.append(f"[file:{comp.name or 'file'}]")
            elif isinstance(comp, Node | Nodes):
                parts.append(self._nodes_to_text(comp))
            elif isinstance(comp, Json):
                parts.append(self._json_fallback(comp))
            else:
                parts.append(f"[{comp.__class__.__name__}]")
        return "".join(parts).strip()

    @staticmethod
    def _json_fallback(comp: Json) -> str:
        return f"[json:{comp.data}]"

    @staticmethod
    def _music_fallback(comp: Music) -> str:
        title = comp.title or "music"
        url = comp.url or comp.audio or ""
        return f"[music:{title}] {url}".strip()

    @staticmethod
    def _share_xml(share: Share) -> str:
        title = escape(share.title or "")
        desc = escape(share.content or "")
        url = escape(share.url or "")
        thumb = escape(share.image or "")
        return (
            '<appmsg appid="" sdkver="0">'
            f"<title>{title}</title>"
            f"<des>{desc}</des>"
            "<action></action>"
            "<type>5</type>"
            "<showtype>0</showtype>"
            "<content></content>"
            f"<url>{url}</url>"
            f"<thumburl>{thumb}</thumburl>"
            "</appmsg>"
        )
