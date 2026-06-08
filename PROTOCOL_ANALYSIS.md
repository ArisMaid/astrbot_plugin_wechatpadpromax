# WeChatPadProMAX 协议能力分析

本文记录 WeChatPadProMAX 消息接口、AstrBot 消息组件，以及未来对标 NapCat 的独立协议端方案之间的映射关系。

## 信息来源

- 本地 Swagger：`wechatpadpromax08_202606021509_windows_amd64/swagger/swagger.json`
- 在线文档：<https://wx.knowhub.cloud/>
- AstrBot OneBot v11 适配器与 `astrbot/core` 下的消息组件实现

本分析过程没有调用登录、初始化、心跳或真实消息发送接口。

## WeChatPadProMAX 消息接口

### 直接发送接口

| WeChatPadProMAX 接口 | 用途 | 主要请求字段 | AstrBot 映射 |
| --- | --- | --- | --- |
| `/Msg/SendTxt` | 发送文本和群聊提及 | `ToWxid`、`Content`、`Type`、`At` | `Plain`、`At`、`AtAll` |
| `/Msg/UploadImg` | 上传并发送图片 | `ToWxid`、`Base64` | `Image` |
| `/Msg/SendVoice` | 发送语音 | `ToWxid`、`Base64`、`Type`、`VoiceTime` | `Record`、TTS 输出 |
| `/Msg/SendVideo` | 发送视频 | `ToWxid`、`Base64`、`ImageBase64`、`PlayLength` | `Video` |
| `/Msg/Quote` | 引用回复文本消息 | `ToWxid`、`NewMsgId`、`MsgSeq`、`QuoteContent`、`MsgContent` 等 | 后续可映射 `Reply` |
| `/Msg/Revoke` | 撤回消息 | `ToUserName`、`NewMsgId`、`ClientMsgId`、`CreateTime` | 后续可做管理/动作支持 |
| `/Msg/ShareLink` | 发送链接类应用消息 | `ToWxid`、`Type`、`Xml` | `Share` |
| `/Msg/ShareLocation` | 发送位置 | `ToWxid`、`X`、`Y`、`Scale`、`Label`、`Poiname`、`Infourl` | `Location` |
| `/Msg/ShareCard` | 发送名片 | `ToWxid`、`CardWxId`、`CardNickName`、`CardAlias` | 后续可支持联系人消息 |
| `/Msg/SendXCX` | 发送小程序 XML | `ToWxid`、`Content` | 后续可支持 appmsg XML |
| `/Msg/SendEmoji` | 通过 MD5 发送表情 | `ToWxid`、`Md5`、`TotalLen` | 后续可支持 `Face`/表情 |

### 转发/重发接口

| WeChatPadProMAX 接口 | 用途 | 说明 |
| --- | --- | --- |
| `/Msg/SendCDNImg` | 重发 CDN 图片 XML | 需要已有的已接收图片 XML，不是通用图片上传。 |
| `/Msg/SendCDNVideo` | 重发 CDN 视频 XML | 需要已有的已接收视频 XML，不是通用视频上传。 |
| `/Msg/SendCDNFile` | 重发 CDN 文件 XML | 需要已有的已接收文件 XML，不是通用文件上传。 |
| `/Msg/SendApp` | 群发/群内应用消息 | Swagger 标注为群发能力，使用时需要谨慎。 |

当前结论：WeChatPadProMAX 已提供可用的文本、图片、语音和视频直接发送接口。通用文件上传到聊天、原生合并转发发送，在已检查的 Swagger 中暂未看到明确等价接口。

## WeChatPadProMAX 接收/下载接口

| 接口 | 用途 | 可能的 AstrBot 映射 |
| --- | --- | --- |
| `/Msg/StartAutoSync` | 启动自动消息同步 | 启动同步，当前可通过配置控制。 |
| `/Msg/Sync` | 手动同步 | 除非明确需要，否则不建议常规调用。 |
| `/Tools/DownloadImg` | 下载图片 | 转为 `Image`，可配合本地缓存/文件服务 |
| `/Tools/CdnDownloadImage` | 下载 CDN 高清图片 | 后续可用于提升入站图片质量 |
| `/Tools/DownloadVoice` | 下载语音 | 转为 `Record`，便于 STT/TTS 相关插件处理 |
| `/Tools/DownloadVideo` | 下载视频 | 转为 `Video` |
| `/Tools/DownloadFile` | 下载文件附件 | 转为 `File` |
| `/Tools/UploadFile` | 上传文件数据 | Swagger 中偏上传能力，发送语义仍需确认。 |

当前接收侧采用尽力策略：文本直接转换；图片、语音、视频和文件会优先使用 webhook 中已有的 URL/base64/path；字段足够时可继续调用 `/Tools/Download*`；如果媒体仍无法解析，则回退为可见文本占位。

## 插件已实现能力

插件已将事件回复和主动发送统一到共享发送器：

| AstrBot 组件 | 当前行为 |
| --- | --- |
| `Plain` | 通过 `/Msg/SendTxt` 发送 |
| `At` / `AtAll` | 通过 `/Msg/SendTxt` 的 `At` 字段发送，并保留可见提及文本 |
| `Image` | 通过 `/Msg/UploadImg` 发送 |
| `Record` | 通过 `/Msg/SendVoice` 发送，可修复 AstrBot TTS 生成成功但发送失败的问题 |
| `Video` | 通过 `/Msg/SendVideo` 发送 |
| 图片/音频/视频类 `File` | 根据文件扩展名重路由到图片、语音或视频发送 |
| 普通 `File` | 文本降级 |
| `Node` / `Nodes` | 合并转发文本摘要降级 |
| `Share` | 尽力转换为 `/Msg/ShareLink` XML |
| `Location` | 尽力通过 `/Msg/ShareLocation` 发送 |
| 不支持的消息段 | 可按配置降级为文本 |
| 入站 `Image` / `Record` / `Video` / `File` | 尽力使用 webhook 媒体引用或 `/Tools/Download*` 增强 |

HTTP 客户端也会识别明确的业务失败信号，例如 `Success=false`、`ok=false`、非零 `errcode`、非零 `Ret` 和 `status=error/fail`。这样可以减少“AstrBot 显示发送了，但微信侧没有实际收到”的体验问题。

## 后续可优化方向

1. 引用回复：当原始 webhook payload 中有 `NewMsgId`、`MsgSeq`、发送者和引用内容时，将 AstrBot 的 `Reply + Plain` 映射到 `/Msg/Quote`。

2. CDN 重发：保留已接收图片、视频、文件 appmsg 的原始 XML，让收到过的媒体可以通过 `/Msg/SendCDN*` 重发。

3. 富应用消息：在拿到真实 payload 验证 XML 要求后，再补小程序、名片、音乐、链接等显式模板。

4. 发送可观测性：记录消息段类型、目标 wxid、API 路径、耗时，以及 WeChatPadProMAX 返回的消息标识。

## 对标 NapCat 的独立协议端路线

独立网关仍然可行，也是最接近 NapCatQQ 的长期架构：

```text
WeChatPadProMAX webhook/API
        |
wechatpadpromax-onebot-bridge
        |
OneBot v11 反向 WebSocket
        |
AstrBot 原生 aiocqhttp 适配器
```

关键设计点：

1. AstrBot 作为 OneBot v11 反向 WebSocket 服务端，桥接服务作为协议端客户端。

2. OneBot 兼容性需要稳定数字 ID，但微信 wxid 不是数字。桥接服务需要持久化类似 `wxid -> int64`、`chatroom wxid -> int64` 的映射，并在扩展字段中保留原始 wxid。

3. 先实现最小可用 OneBot 动作：`send_msg`、`send_private_msg`、`send_group_msg`、`get_msg`、`get_group_info`、`get_group_member_info`、`get_group_member_list`。

4. 由于 WeChatPadProMAX 暂未确认有通用原生合并转发接口，`send_group_forward_msg` 和 `send_private_forward_msg` 仍建议先做文本渲染降级。

5. 媒体缓存、下载、上传、时长检测、重试、限速等能力应集中在桥接服务中，而不是散落在 AstrBot 插件内部。

6. AstrBot 插件保留为轻量部署方案；需要最大化 OneBot 生态兼容时，再使用独立桥接服务。
