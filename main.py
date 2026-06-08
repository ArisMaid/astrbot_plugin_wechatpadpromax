from __future__ import annotations

import uuid
from copy import deepcopy
from typing import Any

from astrbot.api import logger, star

from .wechatpadpromax_adapter import ADAPTER_NAME, DEFAULT_CONFIG

SYNCABLE_PLATFORM_KEYS = (
    "base_url",
    "authcode",
    "auto_register_webhook",
    "auto_start_heartbeat",
    "auto_start_sync",
    "diagnostic_latency_log",
    "webhook_url",
    "webhook_public_base_url",
    "webhook_secret",
    "webhook_host",
    "webhook_port",
    "webhook_path",
    "message_types",
    "accepted_msg_types",
    "include_self_message",
    "self_wxid",
    "timeout_seconds",
    "dedupe_cache_size",
    "unified_webhook_mode",
    "webhook_uuid",
    "unsupported_component_fallback",
    "forward_fallback_max_chars",
    "download_inbound_media",
    "inbound_media_fallback_text",
    "inbound_media_cache_dir",
    "inbound_media_download_section_len",
)

PRESERVE_EMPTY_STRING_KEYS = {
    "authcode",
    "webhook_url",
    "webhook_public_base_url",
    "webhook_secret",
    "self_wxid",
    "webhook_uuid",
    "inbound_media_cache_dir",
}

MANAGED_USAGE_NOTE = (
    "这是 WeChatPadProMAX 的主配置入口。插件会自动创建并维护 AstrBot "
    "内部的 wechatpadpromax 机器人平台配置；迁移时优先备份本插件目录和 "
    "data/config/astrbot_plugin_wechatpadpromax_config.json。一般不需要再手动编辑"
    "“机器人”页面里的同名平台。"
)

LEGACY_USAGE_NOTE_MARKERS = (
    "同步到机器人配置",
    "实际运行仍使用 AstrBot 原生机器人平台配置",
)


@star.register(
    "astrbot_plugin_wechatpadpromax",
    "Codex",
    "Platform adapter for connecting WeChatPadProMAX to AstrBot.",
    "0.3.1",
)
class WechatPadProMaxPlugin(star.Star):
    def __init__(self, context: star.Context, config: dict | None = None) -> None:
        super().__init__(context, config)
        self.config = config or {}
        from .wechatpadpromax_adapter import WechatPadProMaxAdapter  # noqa: F401

    async def initialize(self) -> None:
        self._migrate_plugin_config()
        if not self._is_platform_management_enabled():
            return
        await self._sync_config_to_platform()

    def _migrate_plugin_config(self) -> None:
        changed = False
        usage_note = str(self.config.get("usage_note", ""))
        if not usage_note or any(
            marker in usage_note for marker in LEGACY_USAGE_NOTE_MARKERS
        ):
            self.config["usage_note"] = MANAGED_USAGE_NOTE
            changed = True

        if "sync_to_platform" in self.config:
            if "manage_platform_config" not in self.config:
                self.config["manage_platform_config"] = True
            self.config.pop("sync_to_platform", None)
            changed = True

        if changed:
            self._save_plugin_config()

    def _is_platform_management_enabled(self) -> bool:
        if "manage_platform_config" in self.config:
            return bool(self.config.get("manage_platform_config"))
        return True

    async def _sync_config_to_platform(self) -> None:
        core_config = self.context.get_config()
        platforms = core_config.setdefault("platform", [])
        platform_id = (
            str(self.config.get("platform_id") or DEFAULT_CONFIG["id"]).strip()
            or DEFAULT_CONFIG["id"]
        )

        index, current_platform = self._find_platform(platforms, platform_id)
        if not self.config.get("platform_config_imported", False):
            imported = self._import_existing_platform_config(current_platform)
            self.config["platform_config_imported"] = True
            if imported or hasattr(self.config, "save_config"):
                self._save_plugin_config()

        if self.config.get("unified_webhook_mode") and not self.config.get(
            "webhook_uuid"
        ):
            self.config["webhook_uuid"] = uuid.uuid4().hex
            self._save_plugin_config()

        next_platform = deepcopy(current_platform or DEFAULT_CONFIG)
        next_platform["id"] = platform_id
        next_platform["type"] = ADAPTER_NAME
        next_platform["enable"] = bool(
            self.config.get("enable", next_platform.get("enable", True))
        )

        for key in SYNCABLE_PLATFORM_KEYS:
            if key not in self.config:
                continue
            value = self.config.get(key)
            if self._should_skip_empty_value(key, value, current_platform):
                continue
            next_platform[key] = value

        if index is None:
            platforms.append(next_platform)
        else:
            platforms[index] = next_platform

        if hasattr(core_config, "save_config"):
            core_config.save_config()

        await self._reload_platform_if_running(next_platform)
        logger.info(
            "[WeChatPadProMAX] plugin configuration synced to platform %s.",
            platform_id,
        )

    def _import_existing_platform_config(
        self,
        current_platform: dict[str, Any] | None,
    ) -> bool:
        if not current_platform:
            return False

        changed = False
        for key in ("enable", *SYNCABLE_PLATFORM_KEYS):
            if key not in current_platform:
                continue

            current_value = current_platform.get(key)
            plugin_has_value = key in self.config
            plugin_value = self.config.get(key)
            default_value = DEFAULT_CONFIG.get(key)

            should_import = not plugin_has_value
            should_import = should_import or (
                isinstance(plugin_value, str)
                and not plugin_value
                and current_value not in ("", None)
            )
            should_import = should_import or (
                key in DEFAULT_CONFIG
                and plugin_value == default_value
                and current_value != default_value
            )

            if should_import:
                self.config[key] = deepcopy(current_value)
                changed = True

        return changed

    def _save_plugin_config(self) -> None:
        save_config = getattr(self.config, "save_config", None)
        if callable(save_config):
            save_config()

    @staticmethod
    def _find_platform(
        platforms: list[dict[str, Any]],
        platform_id: str,
    ) -> tuple[int | None, dict[str, Any] | None]:
        for index, platform in enumerate(platforms):
            if (
                platform.get("id") == platform_id
                and platform.get("type") == ADAPTER_NAME
            ):
                return index, platform
        return None, None

    def _should_skip_empty_value(
        self,
        key: str,
        value: Any,
        current_platform: dict[str, Any] | None,
    ) -> bool:
        if not isinstance(value, str) or value:
            return False
        if key == "webhook_url" and self.config.get("webhook_public_base_url"):
            return False
        return bool(
            key in PRESERVE_EMPTY_STRING_KEYS
            and current_platform
            and current_platform.get(key)
        )

    async def _reload_platform_if_running(
        self, platform_config: dict[str, Any]
    ) -> None:
        platform_manager = getattr(self.context, "platform_manager", None)
        if not platform_manager:
            return

        get_insts = getattr(platform_manager, "get_insts", None)
        instances = list(get_insts() if callable(get_insts) else [])
        platform_id = platform_config["id"]
        is_running = any(inst.meta().id == platform_id for inst in instances)
        has_core_started = any(inst.meta().id == "webchat" for inst in instances)

        if is_running and hasattr(platform_manager, "reload"):
            await platform_manager.reload(platform_config)
        elif (
            has_core_started
            and platform_config.get("enable", True)
            and hasattr(platform_manager, "load_platform")
        ):
            await platform_manager.load_platform(platform_config)
