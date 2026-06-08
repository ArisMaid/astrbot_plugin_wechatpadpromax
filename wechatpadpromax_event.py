from __future__ import annotations

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import At, Image, Plain
from astrbot.api.platform import AstrBotMessage, PlatformMetadata

from .wechatpadpromax_client import WechatPadProMaxClient


class WechatPadProMaxMessageEvent(AstrMessageEvent):
    def __init__(
        self,
        message_str: str,
        message_obj: AstrBotMessage,
        platform_meta: PlatformMetadata,
        session_id: str,
        client: WechatPadProMaxClient,
    ) -> None:
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.client = client

    @staticmethod
    def _target_from_message(message_obj: AstrBotMessage) -> str:
        raw_message = (
            message_obj.raw_message if isinstance(message_obj.raw_message, dict) else {}
        )
        if raw_message.get("_reply_target"):
            return str(raw_message["_reply_target"])
        return message_obj.group_id or message_obj.session_id

    @staticmethod
    def _extract_plain_and_at(message_chain: MessageChain) -> tuple[str, str]:
        text_parts: list[str] = []
        at_targets: list[str] = []
        for comp in message_chain.chain:
            if isinstance(comp, Plain):
                text_parts.append(comp.text)
            elif isinstance(comp, At):
                target = str(comp.qq).strip()
                if target and target != "all":
                    at_targets.append(target)
                label = comp.name or target
                if label:
                    text_parts.append(f"@{label}")
        return "".join(text_parts).strip(), ",".join(at_targets)

    async def send(self, message: MessageChain) -> None:
        target = self._target_from_message(self.message_obj)
        if not target:
            logger.warning("[WeChatPadProMAX] skip send: missing target wxid")
            await super().send(message)
            return

        text, at = self._extract_plain_and_at(message)
        if text:
            await self.client.send_text(target, text, at=at)

        for comp in message.chain:
            if not isinstance(comp, Image):
                continue
            try:
                image_base64 = await comp.convert_to_base64()
                await self.client.send_image_base64(target, image_base64)
            except Exception as e:
                logger.warning("[WeChatPadProMAX] image send failed: %s", e)

        await super().send(message)
