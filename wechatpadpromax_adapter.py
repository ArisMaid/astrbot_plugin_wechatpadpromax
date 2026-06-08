from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import re
import time
import uuid
import xml.etree.ElementTree as ET
from collections import OrderedDict
from typing import Any

import quart

from astrbot.api import logger
from astrbot.api.event import MessageChain
from astrbot.api.message_components import Image, Plain
from astrbot.api.platform import (
    AstrBotMessage,
    Group,
    MessageMember,
    MessageType,
    Platform,
    PlatformMetadata,
    register_platform_adapter,
)
from astrbot.core.platform.astr_message_event import MessageSesion

from .wechatpadpromax_client import WechatPadProMaxClient
from .wechatpadpromax_event import WechatPadProMaxMessageEvent

ADAPTER_NAME = "wechatpadpromax"

DEFAULT_CONFIG = {
    "id": "wechatpadpromax",
    "type": ADAPTER_NAME,
    "enable": True,
    "base_url": "http://127.0.0.1:8062",
    "authcode": "",
    "auto_register_webhook": True,
    "auto_start_heartbeat": False,
    "auto_start_sync": True,
    "diagnostic_latency_log": True,
    "webhook_url": "",
    "webhook_public_base_url": "",
    "webhook_secret": "",
    "webhook_host": "0.0.0.0",
    "webhook_port": 6197,
    "webhook_path": "/webhook/wechatpadpromax",
    "message_types": ["*"],
    "accepted_msg_types": ["1", "3", "34", "43", "49"],
    "include_self_message": False,
    "self_wxid": "",
    "timeout_seconds": 15,
    "dedupe_cache_size": 512,
    "unified_webhook_mode": False,
    "webhook_uuid": "",
}

CONFIG_METADATA = {
    "base_url": {
        "description": "WeChatPadProMAX API base URL",
        "type": "string",
        "hint": "Address AstrBot uses to call WeChatPadProMAX. Example: http://127.0.0.1:8062 or http://192.168.1.20:8062.",
    },
    "authcode": {
        "description": "Authcode",
        "type": "string",
        "hint": "Required for webhook registration, message sync, and sending replies.",
    },
    "webhook_url": {
        "description": "Full webhook callback URL",
        "type": "string",
        "hint": "Optional override registered to WeChatPadProMAX. Use this when AstrBot is behind a reverse proxy, for example: https://bot.example.com/webhook/wechatpadpromax.",
    },
    "webhook_public_base_url": {
        "description": "Webhook public base URL",
        "type": "string",
        "hint": "Optional base URL that WeChatPadProMAX can reach. Example: http://192.168.1.10:6197. Ignored when Full webhook callback URL is set.",
    },
    "webhook_secret": {
        "description": "Webhook secret",
        "type": "string",
        "hint": "Optional. Must match the secret registered in WeChatPadProMAX to verify webhook signatures.",
    },
    "webhook_host": {
        "description": "Webhook listen host",
        "type": "string",
        "hint": "Local address AstrBot listens on. Use 0.0.0.0 when WeChatPadProMAX is on another machine.",
    },
    "webhook_port": {
        "description": "Webhook listen port",
        "type": "int",
        "hint": "Local port used by the built-in webhook server when unified webhook mode is disabled.",
    },
    "webhook_path": {
        "description": "Webhook path",
        "type": "string",
        "hint": "Path used by the built-in webhook server.",
    },
    "auto_register_webhook": {
        "description": "Auto register webhook",
        "type": "bool",
        "hint": "When enabled, the adapter calls WeChatPadProMAX /Webhook/Set on startup or reload.",
    },
    "auto_start_heartbeat": {
        "description": "Auto start heartbeat",
        "type": "bool",
        "hint": "When enabled, the adapter calls WeChatPadProMAX /Login/AutoHeartBeat on startup or reload. Keep disabled unless you explicitly need it.",
    },
    "auto_start_sync": {
        "description": "Auto start message sync",
        "type": "bool",
        "hint": "When enabled, the adapter calls WeChatPadProMAX /Msg/StartAutoSync after startup.",
    },
    "diagnostic_latency_log": {
        "description": "Log webhook latency diagnostics",
        "type": "bool",
        "hint": "When enabled, the adapter logs message timestamp-to-webhook latency for troubleshooting delayed delivery.",
    },
    "message_types": {
        "description": "Webhook message type filter",
        "type": "list",
        "hint": "Passed to WeChatPadProMAX /Webhook/Set. Keep * unless you need to limit event types.",
    },
    "accepted_msg_types": {
        "description": "Accepted WeChat msgType values",
        "type": "list",
        "hint": "Message msgType values converted into AstrBot messages. Defaults: 1=text, 3=image, 34=voice, 43=video, 49=app message.",
    },
    "include_self_message": {
        "description": "Include self messages",
        "type": "bool",
        "hint": "Whether to pass messages sent by the logged-in WeChat account into AstrBot.",
    },
    "self_wxid": {
        "description": "Bot wxid override",
        "type": "string",
        "hint": "Optional. Leave empty to infer from the webhook payload.",
    },
    "timeout_seconds": {
        "description": "API timeout seconds",
        "type": "int",
        "hint": "Timeout for AstrBot requests to WeChatPadProMAX.",
    },
    "dedupe_cache_size": {
        "description": "Dedupe cache size",
        "type": "int",
        "hint": "Number of recent message IDs kept to avoid duplicate webhook delivery.",
    },
    "unified_webhook_mode": {
        "description": "Use AstrBot unified webhook",
        "type": "bool",
        "hint": "Advanced. When enabled, AstrBot receives callbacks through /api/platform/webhook/<uuid> instead of the adapter's own port.",
    },
    "webhook_uuid": {
        "description": "Unified webhook UUID",
        "type": "string",
        "hint": "Generated by AstrBot when unified webhook mode is enabled. Usually leave it unchanged.",
    },
}

I18N_RESOURCES = {
    "zh-CN": {
        "base_url": {
            "description": "WeChatPadProMAX API 地址",
            "hint": "AstrBot 调用 WeChatPadProMAX 的地址。例如：http://127.0.0.1:8062 或 http://192.168.1.20:8062。",
        },
        "authcode": {
            "description": "授权码",
            "hint": "用于注册 webhook、启动消息同步和发送回复。",
        },
        "webhook_url": {
            "description": "完整 webhook 回调地址",
            "hint": "可选。会直接注册到 WeChatPadProMAX。例如反向代理场景可填：https://bot.example.com/webhook/wechatpadpromax。",
        },
        "webhook_public_base_url": {
            "description": "webhook 对外基础地址",
            "hint": "可选。填写 WeChatPadProMAX 能访问到的 AstrBot webhook 基础地址，例如：http://192.168.1.10:6197。填写完整 webhook 回调地址时此项会被忽略。",
        },
        "webhook_secret": {
            "description": "webhook 密钥",
            "hint": "可选。需要与 WeChatPadProMAX 注册的 secret 一致，用于校验回调签名。",
        },
        "webhook_host": {
            "description": "webhook 监听地址",
            "hint": "AstrBot 本机监听地址。WeChatPadProMAX 部署在其他机器时建议使用 0.0.0.0。",
        },
        "webhook_port": {
            "description": "webhook 监听端口",
            "hint": "未启用统一 webhook 模式时，插件内置 webhook 服务监听的本机端口。",
        },
        "webhook_path": {
            "description": "webhook 路径",
            "hint": "插件内置 webhook 服务使用的路径。",
        },
        "auto_register_webhook": {
            "description": "自动注册 webhook",
            "hint": "启用后，适配器启动或重载时会调用 WeChatPadProMAX /Webhook/Set。",
        },
        "auto_start_sync": {
            "description": "自动启动消息同步",
            "hint": "启用后，适配器启动后会调用 WeChatPadProMAX /Msg/StartAutoSync。",
        },
        "message_types": {
            "description": "webhook 事件类型过滤",
            "hint": "传给 WeChatPadProMAX /Webhook/Set。一般保持 * 即可。",
        },
        "accepted_msg_types": {
            "description": "接收的微信 msgType",
            "hint": "会转换成 AstrBot 消息的 msgType。默认：1=文本，3=图片，34=语音，43=视频，49=应用消息。",
        },
        "include_self_message": {
            "description": "包含自己发送的消息",
            "hint": "是否把登录微信号自己发送的消息也交给 AstrBot。",
        },
        "self_wxid": {
            "description": "机器人 wxid 覆盖",
            "hint": "可选。留空时从 webhook payload 自动推断。",
        },
        "timeout_seconds": {
            "description": "API 超时时间（秒）",
            "hint": "AstrBot 请求 WeChatPadProMAX API 的超时时间。",
        },
        "dedupe_cache_size": {
            "description": "去重缓存大小",
            "hint": "保存最近多少个消息 ID，用于避免 webhook 重复投递。",
        },
        "unified_webhook_mode": {
            "description": "使用 AstrBot 统一 webhook",
            "hint": "高级选项。启用后通过 /api/platform/webhook/<uuid> 接收回调，而不是使用插件自己的端口。",
        },
        "webhook_uuid": {
            "description": "统一 webhook UUID",
            "hint": "启用统一 webhook 模式时由 AstrBot 生成，通常不需要手动修改。",
        },
    },
    "en-US": {
        "base_url": {
            "description": "WeChatPadProMAX API base URL",
            "hint": "Address AstrBot uses to call WeChatPadProMAX. Example: http://127.0.0.1:8062 or http://192.168.1.20:8062.",
        },
        "authcode": {
            "description": "Authcode",
            "hint": "Required for webhook registration, message sync, and sending replies.",
        },
        "webhook_url": {
            "description": "Full webhook callback URL",
            "hint": "Optional override registered to WeChatPadProMAX. Example: https://bot.example.com/webhook/wechatpadpromax.",
        },
        "webhook_public_base_url": {
            "description": "Webhook public base URL",
            "hint": "Optional base URL that WeChatPadProMAX can reach. Example: http://192.168.1.10:6197. Ignored when Full webhook callback URL is set.",
        },
        "webhook_secret": {
            "description": "Webhook secret",
            "hint": "Optional. Must match the secret registered in WeChatPadProMAX to verify webhook signatures.",
        },
        "webhook_host": {
            "description": "Webhook listen host",
            "hint": "Local address AstrBot listens on. Use 0.0.0.0 when WeChatPadProMAX is on another machine.",
        },
        "webhook_port": {
            "description": "Webhook listen port",
            "hint": "Local port used by the built-in webhook server when unified webhook mode is disabled.",
        },
        "webhook_path": {
            "description": "Webhook path",
            "hint": "Path used by the built-in webhook server.",
        },
        "auto_register_webhook": {
            "description": "Auto register webhook",
            "hint": "When enabled, the adapter calls WeChatPadProMAX /Webhook/Set on startup or reload.",
        },
        "auto_start_sync": {
            "description": "Auto start message sync",
            "hint": "When enabled, the adapter calls WeChatPadProMAX /Msg/StartAutoSync after startup.",
        },
        "message_types": {
            "description": "Webhook message type filter",
            "hint": "Passed to WeChatPadProMAX /Webhook/Set. Keep * unless you need to limit event types.",
        },
        "accepted_msg_types": {
            "description": "Accepted WeChat msgType values",
            "hint": "Message msgType values converted into AstrBot messages. Defaults: 1=text, 3=image, 34=voice, 43=video, 49=app message.",
        },
        "include_self_message": {
            "description": "Include self messages",
            "hint": "Whether to pass messages sent by the logged-in WeChat account into AstrBot.",
        },
        "self_wxid": {
            "description": "Bot wxid override",
            "hint": "Optional. Leave empty to infer from the webhook payload.",
        },
        "timeout_seconds": {
            "description": "API timeout seconds",
            "hint": "Timeout for AstrBot requests to WeChatPadProMAX.",
        },
        "dedupe_cache_size": {
            "description": "Dedupe cache size",
            "hint": "Number of recent message IDs kept to avoid duplicate webhook delivery.",
        },
        "unified_webhook_mode": {
            "description": "Use AstrBot unified webhook",
            "hint": "Advanced. When enabled, AstrBot receives callbacks through /api/platform/webhook/<uuid> instead of the adapter's own port.",
        },
        "webhook_uuid": {
            "description": "Unified webhook UUID",
            "hint": "Generated by AstrBot when unified webhook mode is enabled. Usually leave it unchanged.",
        },
    },
}


class WechatPadProMaxServer:
    def __init__(
        self,
        host: str,
        port: int,
        path: str,
        callback: Any,
    ) -> None:
        self.host = host
        self.port = port
        self.path = path if path.startswith("/") else f"/{path}"
        self.callback = callback
        self.app = quart.Quart(__name__)
        self.shutdown_event = asyncio.Event()
        self.app.add_url_rule(self.path, view_func=self.health, methods=["GET"])
        self.app.add_url_rule(self.path, view_func=self.handle, methods=["POST"])

    async def health(self):
        return {"status": "ok", "adapter": ADAPTER_NAME}, 200

    async def handle(self):
        return await self.callback(quart.request)

    async def run(self) -> None:
        logger.info(
            "[WeChatPadProMAX] webhook server listening on %s:%d%s",
            self.host,
            self.port,
            self.path,
        )
        await self.app.run_task(
            host=self.host,
            port=self.port,
            shutdown_trigger=self.shutdown_trigger,
        )

    async def shutdown_trigger(self) -> None:
        await self.shutdown_event.wait()

    async def shutdown(self) -> None:
        self.shutdown_event.set()
        try:
            await self.app.shutdown()
        except Exception:
            pass


@register_platform_adapter(
    ADAPTER_NAME,
    "WeChatPadProMAX platform adapter.",
    default_config_tmpl=DEFAULT_CONFIG,
    adapter_display_name="WeChatPadProMAX",
    support_streaming_message=False,
    config_metadata=CONFIG_METADATA,
    i18n_resources=I18N_RESOURCES,
)
class WechatPadProMaxAdapter(Platform):
    def __init__(
        self,
        platform_config: dict,
        platform_settings: dict,
        event_queue: asyncio.Queue,
    ) -> None:
        super().__init__(platform_config, event_queue)
        self.settings = platform_settings
        self.client = WechatPadProMaxClient(
            base_url=str(self.config.get("base_url") or DEFAULT_CONFIG["base_url"]),
            authcode=str(self.config.get("authcode") or ""),
            timeout_seconds=int(self.config.get("timeout_seconds") or 15),
        )
        self.host = str(self.config.get("webhook_host") or "0.0.0.0")
        self.port = int(self.config.get("webhook_port") or 6197)
        self.path = str(self.config.get("webhook_path") or "/webhook/wechatpadpromax")
        self.secret = str(self.config.get("webhook_secret") or "")
        self.shutdown_event = asyncio.Event()
        self._dedupe_cache_size = int(self.config.get("dedupe_cache_size") or 512)
        self._seen_message_ids: OrderedDict[str, float] = OrderedDict()

        self.server: WechatPadProMaxServer | None = None
        if not self.config.get("unified_webhook_mode"):
            self.server = WechatPadProMaxServer(
                host=self.host,
                port=self.port,
                path=self.path,
                callback=self.webhook_callback,
            )

        self.metadata = PlatformMetadata(
            name=ADAPTER_NAME,
            description="WeChatPadProMAX platform adapter.",
            id=str(self.config.get("id") or ADAPTER_NAME),
            support_streaming_message=False,
            support_proactive_message=bool(self.client.authcode),
        )

    def meta(self) -> PlatformMetadata:
        return self.metadata

    async def run(self) -> None:
        tasks: list[Any] = []
        if self.config.get("auto_register_webhook"):
            tasks.append(self._register_webhook_if_ready())
        if self.config.get("auto_start_heartbeat"):
            tasks.append(self._start_heartbeat_if_ready())
        if self.config.get("auto_start_sync"):
            tasks.append(self._start_sync_if_ready())

        if self.server:
            tasks.append(self.server.run())
        else:
            webhook_uuid = str(self.config.get("webhook_uuid") or "")
            if webhook_uuid:
                logger.info(
                    "[WeChatPadProMAX] using AstrBot unified webhook: "
                    "/api/platform/webhook/%s",
                    webhook_uuid,
                )
            else:
                logger.warning(
                    "[WeChatPadProMAX] unified_webhook_mode is enabled but "
                    "webhook_uuid is empty."
                )
            tasks.append(self.shutdown_event.wait())

        await asyncio.gather(*tasks)

    async def terminate(self) -> None:
        self.shutdown_event.set()
        if self.server:
            await self.server.shutdown()
        await self.client.close()

    async def send_by_session(
        self,
        session: MessageSesion,
        message_chain: MessageChain,
    ) -> None:
        target = session.session_id
        text = "".join(
            comp.text for comp in message_chain.chain if isinstance(comp, Plain)
        ).strip()
        if text:
            try:
                await self.client.send_text(target, text)
            except Exception as e:
                logger.warning("[WeChatPadProMAX] proactive text send failed: %s", e)
        await super().send_by_session(session, message_chain)

    async def webhook_callback(self, request: Any) -> Any:
        raw_body = await request.get_data()
        payload = await self._parse_request_json(request, raw_body)
        if payload is None:
            return {"status": "bad_request", "message": "invalid json"}, 400

        if not self._verify_signature(payload, raw_body):
            return {"status": "unauthorized", "message": "invalid signature"}, 401

        try:
            started_at = time.monotonic()
            handled = await self.handle_webhook_payload(payload)
            elapsed_ms = (time.monotonic() - started_at) * 1000
            if self.config.get("diagnostic_latency_log"):
                logger.info(
                    "[WeChatPadProMAX] webhook handled=%d elapsed=%.1fms",
                    handled,
                    elapsed_ms,
                )
        except Exception as e:
            logger.error(
                "[WeChatPadProMAX] webhook handling failed: %s",
                e,
                exc_info=True,
            )
            return {"status": "error", "message": str(e)}, 500

        return {"status": "ok", "handled": handled}, 200

    async def handle_webhook_payload(self, payload: dict[str, Any]) -> int:
        count = 0
        for message in self._iter_messages(payload):
            if self._should_skip_message(payload, message):
                continue
            msg_id = self._message_id(message)
            if msg_id and self._is_duplicate_message(msg_id):
                logger.debug("[WeChatPadProMAX] duplicate skipped: %s", msg_id)
                continue
            abm = self._convert_message(payload, message)
            if abm is None:
                continue
            self._log_message_latency(payload, message, abm)
            await self.handle_msg(abm)
            count += 1
        return count

    async def handle_msg(self, message: AstrBotMessage) -> None:
        event = WechatPadProMaxMessageEvent(
            message_str=message.message_str,
            message_obj=message,
            platform_meta=self.meta(),
            session_id=message.session_id,
            client=self.client,
        )
        raw_message = (
            message.raw_message if isinstance(message.raw_message, dict) else {}
        )
        route_meta = raw_message.get("_wechatpadpromax_route")
        if isinstance(route_meta, dict):
            for key, value in route_meta.items():
                event.set_extra(f"wechatpadpromax_{key}", value)
        self.commit_event(event)

    async def _parse_request_json(
        self,
        request: Any,
        raw_body: bytes,
    ) -> dict[str, Any] | None:
        try:
            payload = await request.get_json(force=True, silent=True)
        except TypeError:
            payload = None
        if payload is None:
            try:
                payload = json.loads(raw_body.decode("utf-8"))
            except Exception:
                return None
        return payload if isinstance(payload, dict) else None

    def _verify_signature(self, payload: dict[str, Any], raw_body: bytes) -> bool:
        if not self.secret:
            return True

        wxid = str(payload.get("Wxid") or "")
        message_type = str(payload.get("MessageType") or "")
        timestamp = str(payload.get("Timestamp") or "")
        signature = str(payload.get("Signature") or "")
        if not all([wxid, message_type, timestamp, signature]):
            logger.warning("[WeChatPadProMAX] signed webhook missing signature fields")
            return False

        digest_source = f"{wxid}{message_type}{timestamp}{self.secret}"
        expected = hmac.new(
            self.secret.encode("utf-8"),
            digest_source.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if hmac.compare_digest(expected, signature):
            return True

        body_expected = hmac.new(
            self.secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(body_expected, signature)

    def _iter_messages(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        data = self._get_dict(payload, "Data", "data", "TestData", "testData")
        if not data:
            data = payload

        for key in ("messages", "Messages", "message", "Message", "items", "Items"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                return [value]

        sync_data = self._get_dict(data, "syncData", "SyncData")
        if sync_data:
            return self._iter_messages(sync_data)

        if any(key in data for key in ("msgType", "fromUser", "content", "msgId")):
            return [data]
        if any(key in payload for key in ("msgType", "fromUser", "content", "msgId")):
            return [payload]
        return []

    def _should_skip_message(
        self,
        payload: dict[str, Any],
        message: dict[str, Any],
    ) -> bool:
        accepted_types = {str(i) for i in self.config.get("accepted_msg_types", [])}
        msg_type = str(
            self._first_value(message, "msgType", "MsgType", "Type", "type") or ""
        )
        if (
            accepted_types
            and "*" not in accepted_types
            and msg_type not in accepted_types
        ):
            return True

        if self._as_bool(self._first_value(message, "isSelf", "IsSelf")):
            return not bool(self.config.get("include_self_message"))

        event_type = str(payload.get("MessageType") or payload.get("messageType") or "")
        return event_type == "logout"

    def _convert_message(
        self,
        payload: dict[str, Any],
        message: dict[str, Any],
    ) -> AstrBotMessage | None:
        content = str(self._first_value(message, "content", "Content", "text") or "")
        raw_content = str(
            self._first_value(message, "rawContent", "RawContent", "xml") or ""
        )
        from_user = self._normalize_id(
            self._first_value(
                message,
                "fromUser",
                "FromUser",
                "fromWxid",
                "FromWxid",
                "fromUserName",
                "FromUserName",
                "FromUsername",
            )
        )
        to_user = self._normalize_id(
            self._first_value(
                message,
                "toUser",
                "ToUser",
                "toWxid",
                "ToWxid",
                "toUserName",
                "ToUserName",
                "ToUsername",
            )
        )
        is_self = self._as_bool(self._first_value(message, "isSelf", "IsSelf"))
        from_nick = str(
            self._first_value(
                message,
                "senderNick",
                "SenderNick",
                "senderNickname",
                "SenderNickname",
                "fromNick",
                "FromNick",
                "nickname",
            )
            or ""
        )
        bot_wxid = str(
            self.config.get("self_wxid")
            or payload.get("Wxid")
            or payload.get("wxid")
            or to_user
            or self.meta().id
        )

        if not from_user and not to_user:
            logger.debug("[WeChatPadProMAX] skip message without from/to: %s", message)
            return None

        group_id = self._group_id_from_message(message, from_user, to_user)
        is_group = bool(group_id)
        sender_id = from_user
        session_id = from_user
        reply_target = from_user

        if is_group:
            sender_id, content = self._group_sender_and_content(
                message=message,
                content=content,
                from_user=from_user,
                to_user=to_user,
                group_id=group_id,
                bot_wxid=bot_wxid,
                is_self=is_self,
            )
            session_id = group_id
            reply_target = group_id
        elif is_self:
            sender_id = bot_wxid
            session_id = to_user or from_user
            reply_target = to_user or from_user

        chat_type = self._chat_type(
            is_group=is_group,
            is_self=is_self,
            group_id=group_id,
            sender_id=sender_id,
            bot_wxid=bot_wxid,
        )

        msg_type = str(
            self._first_value(message, "msgType", "MsgType", "Type", "type") or "1"
        )
        components, message_str = self._build_components(msg_type, content, raw_content)
        if not components:
            return None

        abm = AstrBotMessage()
        abm.self_id = bot_wxid
        abm.message = components
        abm.message_str = message_str
        abm.raw_message = dict(message)
        abm.raw_message["_webhook_payload"] = payload
        abm.raw_message["_reply_target"] = reply_target
        abm.raw_message["_chat_type"] = chat_type
        abm.raw_message["_group_id"] = group_id
        abm.raw_message["_sender_id"] = sender_id
        abm.raw_message["_from_user"] = from_user
        abm.raw_message["_to_user"] = to_user
        abm.raw_message["_wechatpadpromax_route"] = {
            "chat_type": chat_type,
            "group_id": group_id,
            "sender_id": sender_id,
            "from_user": from_user,
            "to_user": to_user,
            "session_id": session_id,
            "reply_target": reply_target,
        }
        abm.message_id = self._message_id(message) or uuid.uuid4().hex
        abm.timestamp = self._message_timestamp(message, payload)
        abm.sender = MessageMember(
            user_id=sender_id or session_id,
            nickname=from_nick or sender_id or session_id,
        )

        if is_group:
            abm.type = MessageType.GROUP_MESSAGE
            abm.group_id = group_id
            group_name = str(
                self._first_value(
                    message,
                    "groupNick",
                    "GroupNick",
                    "groupName",
                    "GroupName",
                    "roomName",
                    "RoomName",
                )
                or group_id
            )
            abm.group = Group(group_id=group_id, group_name=group_name)
        else:
            abm.type = MessageType.FRIEND_MESSAGE
        abm.session_id = session_id
        return abm

    def _build_components(
        self,
        msg_type: str,
        content: str,
        raw_content: str,
    ) -> tuple[list[Any], str]:
        if msg_type == "1":
            text = content.strip()
            return ([Plain(text=text)], text) if text else ([], "")

        if msg_type == "3":
            image_url = self._first_http_url(content, raw_content)
            if image_url:
                return [Image.fromURL(image_url)], "[image]"
            return [Plain(text="[image]")], "[image]"

        if msg_type == "34":
            return [Plain(text="[voice]")], "[voice]"

        if msg_type == "43":
            return [Plain(text="[video]")], "[video]"

        if msg_type == "49":
            text = self._parse_app_message_text(raw_content or content)
            return [Plain(text=text)], text

        text = content.strip() or f"[msgType:{msg_type}]"
        return [Plain(text=text)], text

    async def _register_webhook_if_ready(self) -> None:
        if not self.client.authcode:
            logger.warning(
                "[WeChatPadProMAX] authcode is empty; skip webhook registration."
            )
            return
        url = self._webhook_registration_url()
        message_types = self.config.get("message_types") or ["*"]
        if isinstance(message_types, str):
            message_types = [item.strip() for item in message_types.split(",") if item]

        try:
            ret = await self.client.set_webhook(
                url=url,
                secret=self.secret,
                message_types=list(message_types),
                include_self_message=bool(self.config.get("include_self_message")),
            )
            logger.info("[WeChatPadProMAX] webhook registered: %s -> %s", url, ret)
        except Exception as e:
            logger.warning("[WeChatPadProMAX] webhook registration failed: %s", e)

    async def _start_heartbeat_if_ready(self) -> None:
        if not self.client.authcode:
            logger.warning("[WeChatPadProMAX] authcode is empty; skip AutoHeartBeat.")
            return
        try:
            ret = await self.client.start_auto_heartbeat()
            logger.info("[WeChatPadProMAX] AutoHeartBeat result: %s", ret)
        except Exception as e:
            logger.warning("[WeChatPadProMAX] AutoHeartBeat failed: %s", e)

    def _webhook_registration_url(self) -> str:
        url = str(self.config.get("webhook_url") or "").strip()
        if url:
            return url

        path = self._webhook_registration_path()
        public_base_url = str(self.config.get("webhook_public_base_url") or "").strip()
        if public_base_url:
            return f"{public_base_url.rstrip('/')}{path}"

        if self.config.get("unified_webhook_mode") and self.config.get("webhook_uuid"):
            return f"http://127.0.0.1:6185{path}"

        return f"http://127.0.0.1:{self.port}{self.path}"

    def _webhook_registration_path(self) -> str:
        if self.config.get("unified_webhook_mode") and self.config.get("webhook_uuid"):
            return f"/api/platform/webhook/{self.config['webhook_uuid']}"
        return self.path

    async def _start_sync_if_ready(self) -> None:
        if not self.client.authcode:
            logger.warning("[WeChatPadProMAX] authcode is empty; skip StartAutoSync.")
            return
        try:
            ret = await self.client.start_auto_sync()
            logger.info("[WeChatPadProMAX] StartAutoSync result: %s", ret)
        except Exception as e:
            logger.warning("[WeChatPadProMAX] StartAutoSync failed: %s", e)

    def _log_message_latency(
        self,
        payload: dict[str, Any],
        message: dict[str, Any],
        abm: AstrBotMessage,
    ) -> None:
        if not self.config.get("diagnostic_latency_log"):
            return

        now = time.time()
        message_ts = self._message_timestamp(message, payload)
        delivery_lag = max(0.0, now - float(message_ts))
        payload_ts = self._payload_timestamp(payload)
        payload_lag = max(0.0, now - payload_ts) if payload_ts else None
        msg_type = str(
            self._first_value(message, "msgType", "MsgType", "Type", "type") or ""
        )
        msg_id = abm.message_id or self._message_id(message) or "-"
        route_meta = (
            abm.raw_message.get("_wechatpadpromax_route", {})
            if isinstance(abm.raw_message, dict)
            else {}
        )
        logger.info(
            "[WeChatPadProMAX] message route msg_id=%s chat_type=%s "
            "msg_type=%s group_id=%s sender_id=%s from_user=%s to_user=%s "
            "session=%s reply_target=%s message_lag=%.3fs payload_lag=%s",
            msg_id,
            self._log_value(route_meta.get("chat_type")),
            msg_type,
            self._log_value(route_meta.get("group_id")),
            self._log_value(route_meta.get("sender_id")),
            self._log_value(route_meta.get("from_user")),
            self._log_value(route_meta.get("to_user")),
            self._log_value(route_meta.get("session_id") or abm.session_id),
            self._log_value(route_meta.get("reply_target")),
            delivery_lag,
            f"{payload_lag:.3f}s" if payload_lag is not None else "n/a",
        )

    def _is_duplicate_message(self, message_id: str) -> bool:
        now = time.monotonic()
        if message_id in self._seen_message_ids:
            return True
        self._seen_message_ids[message_id] = now
        while len(self._seen_message_ids) > self._dedupe_cache_size:
            self._seen_message_ids.popitem(last=False)
        return False

    @staticmethod
    def _message_id(message: dict[str, Any]) -> str:
        value = WechatPadProMaxAdapter._first_value(
            message,
            "newMsgId",
            "NewMsgId",
            "msgId",
            "MsgId",
            "messageId",
            "MessageId",
            "id",
        )
        return str(value or "")

    @staticmethod
    def _message_timestamp(message: dict[str, Any], payload: dict[str, Any]) -> int:
        value = WechatPadProMaxAdapter._first_value(
            message,
            "createTime",
            "CreateTime",
            "timestamp",
            "Timestamp",
        )
        if value is None:
            value = payload.get("Timestamp")
        try:
            ts = int(value)
            return ts // 1000 if ts > 1_000_000_000_000 else ts
        except Exception:
            return int(time.time())

    def _group_id_from_message(
        self,
        message: dict[str, Any],
        from_user: str,
        to_user: str,
    ) -> str:
        explicit_group = self._first_value(
            message,
            "groupId",
            "GroupId",
            "groupWxid",
            "GroupWxid",
            "roomId",
            "RoomId",
            "roomWxid",
            "RoomWxid",
            "chatroomId",
            "ChatroomId",
            "ChatRoomId",
            "chatroomWxid",
            "ChatroomWxid",
            "ChatRoomWxid",
        )
        talker = self._first_value(
            message,
            "talker",
            "Talker",
            "talkerWxid",
            "TalkerWxid",
            "chatUser",
            "ChatUser",
        )
        return self._first_group_id(explicit_group, from_user, to_user, talker)

    def _group_sender_and_content(
        self,
        *,
        message: dict[str, Any],
        content: str,
        from_user: str,
        to_user: str,
        group_id: str,
        bot_wxid: str,
        is_self: bool,
    ) -> tuple[str, str]:
        content_sender, clean_content = self._split_group_sender(content)
        explicit_sender = self._normalize_id(
            self._first_value(
                message,
                "senderWxid",
                "SenderWxid",
                "senderUserName",
                "SenderUserName",
                "SenderUsername",
                "actualSender",
                "ActualSender",
                "actualUserName",
                "ActualUserName",
                "memberWxid",
                "MemberWxid",
                "msgSender",
                "MsgSender",
                "realFromUser",
                "RealFromUser",
            )
        )
        candidates = [content_sender, explicit_sender]
        if from_user and from_user != group_id:
            candidates.append(from_user)
        if to_user and to_user not in {group_id, bot_wxid}:
            candidates.append(to_user)
        if is_self:
            candidates.append(bot_wxid)

        sender_id = next((candidate for candidate in candidates if candidate), group_id)
        return sender_id, clean_content if content_sender else content

    @staticmethod
    def _chat_type(
        *,
        is_group: bool,
        is_self: bool,
        group_id: str,
        sender_id: str,
        bot_wxid: str,
    ) -> str:
        if not is_group:
            return "self" if is_self else "friend"
        if is_self or (bot_wxid and sender_id == bot_wxid):
            return "group_self"
        if sender_id and sender_id != group_id:
            return "group_member"
        return "group_system"

    @staticmethod
    def _payload_timestamp(payload: dict[str, Any]) -> float | None:
        value = payload.get("Timestamp") or payload.get("timestamp")
        try:
            ts = float(value)
            return ts / 1000 if ts > 1_000_000_000_000 else ts
        except Exception:
            return None

    @staticmethod
    def _split_group_sender(content: str) -> tuple[str, str]:
        match = re.match(r"^([^:\n]+):\n?([\s\S]*)$", content or "")
        if not match:
            return "", content
        return match.group(1).strip(), match.group(2)

    @staticmethod
    def _is_group_id(value: str) -> bool:
        return value.endswith("@chatroom")

    @staticmethod
    def _normalize_id(value: Any) -> str:
        return str(value or "").strip()

    @classmethod
    def _first_group_id(cls, *values: Any) -> str:
        for value in values:
            normalized = cls._normalize_id(value)
            if normalized and cls._is_group_id(normalized):
                return normalized
        return ""

    @staticmethod
    def _log_value(value: Any) -> str:
        text = str(value or "").strip()
        return text or "-"

    @staticmethod
    def _get_dict(source: dict[str, Any], *keys: str) -> dict[str, Any]:
        for key in keys:
            value = source.get(key)
            if isinstance(value, dict):
                return value
        return {}

    @staticmethod
    def _first_value(source: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            if key in source and source[key] not in (None, ""):
                return source[key]
        return None

    @staticmethod
    def _as_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return value != 0
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "y"}
        return False

    @staticmethod
    def _first_http_url(*values: str) -> str:
        for value in values:
            match = re.search(r"https?://[^\s\"'<>]+", value or "")
            if match:
                return match.group(0)
        return ""

    @staticmethod
    def _parse_app_message_text(value: str) -> str:
        text = (value or "").strip()
        if not text:
            return "[app message]"
        try:
            root = ET.fromstring(text)
            title = root.findtext(".//title") or ""
            desc = root.findtext(".//des") or ""
            url = root.findtext(".//url") or ""
            parts = [part.strip() for part in (title, desc, url) if part.strip()]
            if parts:
                return "\n".join(parts)
        except Exception:
            pass
        return text[:500] if text else "[app message]"
