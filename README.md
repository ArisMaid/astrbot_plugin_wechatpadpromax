# WeChatPadProMAX for AstrBot

Protocol capability mapping and the NapCat-like gateway roadmap are documented
in [PROTOCOL_ANALYSIS.md](PROTOCOL_ANALYSIS.md).

Current protocol coverage includes text, image, voice/TTS, video, share/location
best-effort sends, merged-forward text fallback, group route diagnostics, and
best-effort inbound media enrichment through WeChatPadProMAX `/Tools/Download*`.

这个插件把 WeChatPadProMAX 作为 AstrBot 平台适配器接入。

安装链接：

```text
https://github.com/ArisMaid/astrbot_plugin_wechatpadpromax
```

推荐配置入口在 AstrBot Dashboard 的「AstrBot 插件」页面，点击 WeChatPadProMAX 插件卡片的齿轮。插件配置会作为主配置源，自动创建并维护 AstrBot 内部的 `wechatpadpromax` 机器人平台配置。

这样独立安装或迁移时，优先备份/恢复插件目录和 `data/config/astrbot_plugin_wechatpadpromax_config.json` 即可；「机器人」页面里的同名平台只是运行时生成的 AstrBot 内部平台实例配置，一般不需要手动维护。

完整参数说明见 [CONFIG.md](CONFIG.md)。

## 常用配置

| 字段 | 说明 |
| --- | --- |
| `base_url` | AstrBot 访问 WeChatPadProMAX API 的地址，例如 `http://127.0.0.1:8062` 或 `http://192.168.1.20:8062`。 |
| `authcode` | WeChatPadProMAX 授权码。绑定 Wxid 后用于注册 webhook、启动同步和发送回复。 |
| `webhook_host` | AstrBot 本机监听地址。分机器部署时通常填 `0.0.0.0`。 |
| `webhook_port` | 插件内置 webhook 服务监听端口，默认 `6197`。 |
| `webhook_path` | 插件内置 webhook 路径，默认 `/webhook/wechatpadpromax`。 |
| `webhook_public_base_url` | WeChatPadProMAX 能访问到的 AstrBot webhook 基础地址，例如 `http://192.168.1.10:6197`。插件会自动拼接 `webhook_path`。 |
| `webhook_url` | 完整 webhook 回调地址。填写后优先级最高，会直接注册到 WeChatPadProMAX。 |
| `auto_register_webhook` | 启动或重载时自动调用 WeChatPadProMAX `/Webhook/Set`。 |
| `auto_start_heartbeat` | 默认关闭。开启后会在启动或重载时调用 WeChatPadProMAX `/Login/AutoHeartBeat`。 |
| `auto_start_sync` | 启动或重载时自动调用 WeChatPadProMAX `/Msg/StartAutoSync`。 |
| `diagnostic_latency_log` | 记录真实 webhook 消息的延迟诊断日志，测试期建议开启。 |

## 部署示例

同一台机器测试：

```text
base_url = http://127.0.0.1:8062
webhook_host = 0.0.0.0
webhook_port = 6197
webhook_public_base_url =
webhook_url = http://127.0.0.1:6197/webhook/wechatpadpromax
```

两台机器部署：

```text
base_url = http://<wechatpadpromax机器IP>:8062
unified_webhook_mode = true
webhook_public_base_url = http://<AstrBot机器IP>:6185
webhook_url =
```

开启 `unified_webhook_mode` 后，插件会自动生成 `webhook_uuid` 并注册：

```text
http://<AstrBot机器IP>:6185/api/platform/webhook/<webhook_uuid>
```

如果不使用统一 webhook，也可以开放 AstrBot 机器的 `6197` 端口，并使用：

```text
webhook_host = 0.0.0.0
webhook_port = 6197
webhook_url = http://<AstrBot机器IP>:6197/webhook/wechatpadpromax
```

使用反向代理：

```text
base_url = http://<wechatpadpromax机器IP>:8062
webhook_url = https://<你的域名>/webhook/wechatpadpromax
```

如果 `webhook_url` 为空，插件会优先用 `webhook_public_base_url + webhook_path` 注册；如果两者都为空，则回落到本机测试地址 `http://127.0.0.1:<webhook_port><webhook_path>`。

## 插件页配置

插件页齿轮读取 `_conf_schema.json`，因此会显示一份可编辑配置。`manage_platform_config` 默认开启，插件启动或重载时会把插件配置同步到同名 `wechatpadpromax` 机器人平台配置并自动加载平台。

如果从旧版本升级，首次启用托管时插件会先把已有「机器人」页面配置里的非默认值导入插件配置，避免覆盖已经配置好的 `base_url`、`authcode`、`webhook_url` 等字段。导入完成后，插件配置就是主配置源。

独立安装或迁移时：

1. 安装或复制插件目录 `data/plugins/astrbot_plugin_wechatpadpromax`。
2. 恢复插件配置文件 `data/config/astrbot_plugin_wechatpadpromax_config.json`。
3. 重载插件或重启 AstrBot。

如果确实想回到 AstrBot 原生「机器人」页面手动维护，可以关闭 `manage_platform_config`。

## 链接安装

在 AstrBot Dashboard 进入「插件市场」或「AstrBot 插件」的安装入口，填写本仓库地址：

```text
https://github.com/ArisMaid/astrbot_plugin_wechatpadpromax
```

安装后进入插件卡片齿轮，至少填写：

```text
base_url = http://<WeChatPadProMAX机器IP>:8062
authcode = <WeChatPadProMAX授权码>
unified_webhook_mode = true
webhook_public_base_url = http://<AstrBot机器IP>:6185
webhook_url =
```

分机器部署时推荐启用 `unified_webhook_mode`，直接走 AstrBot Dashboard 的 `6185` 端口，避免额外开放插件内置 webhook 的 `6197` 端口。

## 延迟诊断

测试期默认开启 `diagnostic_latency_log`。收到真实微信消息时，插件会记录类似下面的日志：

```text
[WeChatPadProMAX] message route msg_id=... chat_type=group_member msg_type=1 group_id=12345@chatroom sender_id=wxid_xxx from_user=12345@chatroom to_user=wxid_bot session=12345@chatroom reply_target=12345@chatroom message_lag=2.345s payload_lag=0.120s
```

其中 `message_lag` 是微信消息时间戳到 AstrBot 收到 webhook 的时间差。如果它很高，瓶颈通常在 WeChatPadProMAX 同步/轮询；如果它很低但回复慢，瓶颈通常在 AstrBot 的规则、模型供应商或发送回复链路。

群聊排查时重点看 `chat_type`、`group_id`、`sender_id` 和 `session`：

- `chat_type=group_member` 表示普通群成员消息，`group_id/session` 是群会话 ID，`sender_id` 是群成员 wxid。
- `chat_type=group_system` 表示未解析出具体成员的群聊系统类消息。
- `chat_type=friend` 表示私聊消息。
