from __future__ import annotations

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.platform import AstrBotMessage, PlatformMetadata

from .wechatpadpromax_client import WechatPadProMaxClient
from .wechatpadpromax_sender import WechatPadProMaxMessageSender


class WechatPadProMaxMessageEvent(AstrMessageEvent):
    def __init__(
        self,
        message_str: str,
        message_obj: AstrBotMessage,
        platform_meta: PlatformMetadata,
        session_id: str,
        client: WechatPadProMaxClient,
        send_config: dict | None = None,
    ) -> None:
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.client = client
        self.send_config = send_config or {}

    @staticmethod
    def _target_from_message(message_obj: AstrBotMessage) -> str:
        raw_message = (
            message_obj.raw_message if isinstance(message_obj.raw_message, dict) else {}
        )
        if raw_message.get("_reply_target"):
            return str(raw_message["_reply_target"])
        return message_obj.group_id or message_obj.session_id

    async def send(self, message: MessageChain) -> None:
        target = self._target_from_message(self.message_obj)
        if not target:
            logger.warning("[WeChatPadProMAX] skip send: missing target wxid")
            await super().send(message)
            return

        sender = WechatPadProMaxMessageSender(self.client, self.send_config)
        await sender.send_chain(target, message)
        await super().send(message)
