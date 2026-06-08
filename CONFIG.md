# 配置参数说明

消息组件支持情况、降级策略和对标 NapCat 的协议端路线见
[PROTOCOL_ANALYSIS.md](PROTOCOL_ANALYSIS.md)。

## 消息发送降级

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `unsupported_component_fallback` | `true` | 将暂不支持的消息段转成文本发送，例如普通文件、合并转发等，避免 AstrBot 显示已发送但微信侧没有实际内容。 |
| `forward_fallback_max_chars` | `4000` | `Node` / `Nodes` 合并转发降级为文本摘要时允许的最大字符数。 |

## 入站媒体

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `download_inbound_media` | `true` | 当 webhook 里没有可直接使用的 URL/base64/path 时，尝试通过 `/Tools/Download*` 下载入站图片、语音、视频和文件，并转换成 AstrBot 的富媒体消息段。 |
| `inbound_media_fallback_text` | `true` | 入站媒体无法解析时保留 `[voice]`、`[file:name]` 等占位文本，而不是静默丢弃消息。 |
| `inbound_media_cache_dir` | 空 | 可选的本地媒体缓存目录，用于保存必须落盘的媒体，例如视频 base64 或文件附件。留空时使用 `data/temp/wechatpadpromax`。 |
| `inbound_media_download_section_len` | `0` | 传给下载接口的 `sectionLen`。保持 `0` 表示使用 webhook 里报告的完整媒体大小；只有服务端要求分片下载时才需要改成正数。 |

适配器会优先使用 webhook 中已经携带的媒体引用。只有无法直接构造 AstrBot 富媒体消息段时，才会调用 WeChatPadProMAX 的下载接口。

本文档是插件配置项的“注释版”说明。AstrBot 实际读取的可编辑配置 schema 在 `_conf_schema.json` 中。

不要把真实 `authcode` 提交到公开仓库。AstrBot 运行时配置会保存在：

```text
data/config/astrbot_plugin_wechatpadpromax_config.json
```

## 核心配置

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `manage_platform_config` | `true` | 插件配置作为主配置源，自动创建/更新 AstrBot 内部 `wechatpadpromax` 平台配置。推荐保持开启，便于迁移和链接安装。 |
| `platform_id` | `wechatpadpromax` | AstrBot 内部平台 ID。通常保持默认；只有同一个 AstrBot 接多个 WeChatPadProMAX 实例时才需要改。 |
| `enable` | `true` | 是否启动插件生成的 AstrBot 平台适配器。 |
| `base_url` | `http://127.0.0.1:8062` | AstrBot 调用 WeChatPadProMAX 的地址。分机器部署时填 WeChatPadProMAX 机器地址，例如 `http://192.168.1.20:8062`。 |
| `authcode` | 空 | WeChatPadProMAX 授权码。用于注册 webhook、启动同步、发送消息。属于敏感配置。 |

## Webhook 配置

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `auto_register_webhook` | `true` | 启动或重载时调用 `/Webhook/Set`，把 AstrBot 回调地址注册到 WeChatPadProMAX。 |
| `webhook_url` | 空 | 完整回调地址，优先级最高。必须指向 AstrBot 机器，而不是 WeChatPadProMAX 机器。 |
| `webhook_public_base_url` | 空 | 当 `webhook_url` 为空时使用。插件会自动拼接内置 webhook 路径或统一 webhook 路径。 |
| `webhook_secret` | 空 | 可选签名密钥。填写后需要与 WeChatPadProMAX 注册配置一致。 |
| `unified_webhook_mode` | `false` | 使用 AstrBot 统一 webhook：`/api/platform/webhook/<webhook_uuid>`。分机器部署或不方便开放 `6197` 时推荐开启。 |
| `webhook_uuid` | 空 | 统一 webhook UUID。开启统一 webhook 且该项为空时，插件会自动生成并保存。 |
| `webhook_host` | `0.0.0.0` | 内置 webhook 监听地址。统一 webhook 模式下不使用。 |
| `webhook_port` | `6197` | 内置 webhook 监听端口。统一 webhook 模式下不使用。 |
| `webhook_path` | `/webhook/wechatpadpromax` | 内置 webhook 路径。统一 webhook 模式下不使用。 |

分机器部署推荐配置：

```text
base_url = http://<WeChatPadProMAX机器IP>:8062
unified_webhook_mode = true
webhook_public_base_url = http://<AstrBot机器IP>:6185
webhook_url =
```

插件最终会注册：

```text
http://<AstrBot机器IP>:6185/api/platform/webhook/<webhook_uuid>
```

如果不用统一 webhook，需要开放 AstrBot 机器的 `6197` 端口：

```text
webhook_host = 0.0.0.0
webhook_port = 6197
webhook_url = http://<AstrBot机器IP>:6197/webhook/wechatpadpromax
```

## 同步与安全

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `auto_start_sync` | `true` | 启动或重载时调用 `/Msg/StartAutoSync` 开始消息同步。 |
| `auto_start_heartbeat` | `false` | 开启后调用 `/Login/AutoHeartBeat`。默认关闭，避免新部署或重载时自动触发心跳接口。 |
| `include_self_message` | `false` | 是否处理登录微信号自己发出的消息。默认关闭，避免消息循环。 |
| `message_types` | `["*"]` | 传给 `/Webhook/Set` 的事件类型过滤。一般保持 `*`。 |
| `accepted_msg_types` | `["1", "3", "34", "43", "49"]` | 转换为 AstrBot 消息的微信 `msgType`。默认包含文本、图片、语音、视频和应用消息。 |
| `self_wxid` | 空 | 机器人 wxid 覆盖。通常留空，由 webhook payload 自动推断。 |
| `timeout_seconds` | `15` | AstrBot 调用 WeChatPadProMAX API 的超时时间。远程/代理部署可适当调大。 |
| `dedupe_cache_size` | `512` | 去重缓存大小，用于避免重复 webhook 投递。 |
| `diagnostic_latency_log` | `true` | 记录真实消息的 webhook 延迟和路由诊断日志。日志会包含 `chat_type`、`group_id`、`sender_id`、`session`，方便区分群成员消息、群系统消息和私聊消息。 |
