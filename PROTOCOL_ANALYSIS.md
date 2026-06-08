# WeChatPadProMAX Protocol Capability Analysis

This document records the current mapping between WeChatPadProMAX message APIs,
AstrBot message components, and a possible NapCat-like protocol gateway.

## Sources

- Local Swagger: `wechatpadpromax08_202606021509_windows_amd64/swagger/swagger.json`
- Online documentation: <https://wx.knowhub.cloud/>
- AstrBot OneBot v11 adapter and message component implementation under `astrbot/core`

No login, init, heartbeat, or real message-send API is called by this analysis.

## WeChatPadProMAX Message APIs

### Direct send APIs

| WeChatPadProMAX API | Purpose | Main body fields | AstrBot mapping |
| --- | --- | --- | --- |
| `/Msg/SendTxt` | Text and group mentions | `ToWxid`, `Content`, `Type`, `At` | `Plain`, `At`, `AtAll` |
| `/Msg/UploadImg` | Upload and send image | `ToWxid`, `Base64` | `Image` |
| `/Msg/SendVoice` | Send voice | `ToWxid`, `Base64`, `Type`, `VoiceTime` | `Record`, TTS output |
| `/Msg/SendVideo` | Send video | `ToWxid`, `Base64`, `ImageBase64`, `PlayLength` | `Video` |
| `/Msg/Quote` | Quote text message | `ToWxid`, `NewMsgId`, `MsgSeq`, `QuoteContent`, `MsgContent`, ... | Future `Reply` support |
| `/Msg/Revoke` | Revoke message | `ToUserName`, `NewMsgId`, `ClientMsgId`, `CreateTime` | Future admin/action support |
| `/Msg/ShareLink` | Share link app message | `ToWxid`, `Type`, `Xml` | `Share` |
| `/Msg/ShareLocation` | Share location | `ToWxid`, `X`, `Y`, `Scale`, `Label`, `Poiname`, `Infourl` | `Location` |
| `/Msg/ShareCard` | Share contact card | `ToWxid`, `CardWxId`, `CardNickName`, `CardAlias` | Future `Contact` support |
| `/Msg/SendXCX` | Send mini program XML | `ToWxid`, `Content` | Future appmsg XML support |
| `/Msg/SendEmoji` | Send emoji by MD5 | `ToWxid`, `Md5`, `TotalLen` | Future `Face`/emoji support |

### Forward/resend APIs

| WeChatPadProMAX API | Purpose | Notes |
| --- | --- | --- |
| `/Msg/SendCDNImg` | Resend CDN image XML | Requires existing received image XML; not a generic upload. |
| `/Msg/SendCDNVideo` | Resend CDN video XML | Requires existing received video XML; not a generic upload. |
| `/Msg/SendCDNFile` | Resend CDN file XML | Requires existing received file XML; not a generic upload. |
| `/Msg/SendApp` | Group/mass app message | Swagger labels it as mass send; use cautiously. |

Current conclusion: WeChatPadProMAX has usable direct APIs for text, image,
voice, and video. Generic file upload-to-chat and native merged forward sending
do not appear to have a direct equivalent in the inspected Swagger.

## WeChatPadProMAX Receive/Download APIs

| API | Purpose | Potential AstrBot mapping |
| --- | --- | --- |
| `/Msg/StartAutoSync` | Start auto message sync | Startup sync; currently optional via config. |
| `/Msg/Sync` | Manual sync | Avoid routine use unless explicitly needed. |
| `/Tools/DownloadImg` | Download image | `Image` with local cache/file service |
| `/Tools/CdnDownloadImage` | Download CDN high-res image | Better inbound image quality |
| `/Tools/DownloadVoice` | Download voice | `Record` for STT/TTS-related plugins |
| `/Tools/DownloadVideo` | Download video | `Video` |
| `/Tools/DownloadFile` | Download file attachment | `File` |
| `/Tools/UploadFile` | Upload file blob | Upload-only in Swagger; send semantics need confirmation. |

Current receive-side plugin behavior is best-effort: text is converted directly;
image, voice, video, and file messages first use URL/base64/path values already
present in the webhook, then optionally call `/Tools/Download*` when the
required IDs and lengths are available, and finally fall back to visible text
placeholders if the media cannot be resolved.

## Implemented In Plugin

The plugin now uses a shared sender for event replies and proactive sends:

| AstrBot component | Current behavior |
| --- | --- |
| `Plain` | Sent via `/Msg/SendTxt` |
| `At` / `AtAll` | Sent via `/Msg/SendTxt` with `At` field and visible mention text |
| `Image` | Sent via `/Msg/UploadImg` |
| `Record` | Sent via `/Msg/SendVoice`; fixes AstrBot TTS send failures |
| `Video` | Sent via `/Msg/SendVideo` |
| image/audio/video `File` | Re-routed to image/voice/video send by file extension |
| generic `File` | Text fallback |
| `Node` / `Nodes` | Text fallback summary for merged forwards |
| `Share` | Best-effort `/Msg/ShareLink` XML |
| `Location` | Best-effort `/Msg/ShareLocation` |
| unsupported components | Optional text fallback controlled by config |
| inbound `Image` / `Record` / `Video` / `File` | Best-effort webhook reference or `/Tools/Download*` enrichment |

The HTTP client also validates explicit business failures such as
`Success=false`, `ok=false`, non-zero `errcode`, non-zero `Ret`, and
`status=error/fail`.
This reduces the "AstrBot says sent but WeChat did not receive it" failure mode.

## Remaining Plugin Optimizations

1. Quote reply:
   map AstrBot `Reply + Plain` to `/Msg/Quote` when the original webhook payload
   has `NewMsgId`, `MsgSeq`, sender, and quote content.

2. CDN resend:
   preserve original received XML for image/video/file app messages so received
   media can be resent through `/Msg/SendCDN*`.

3. Rich appmsg:
   add explicit templates for mini program, contact card, music, and link
   messages only after their XML requirements are verified against real payloads.

4. Send observability:
   log message component type, target wxid, API path, elapsed time, and returned
   message identifiers when WeChatPadProMAX provides them.

## NapCat-like Gateway Roadmap

A standalone gateway remains feasible and is the long-term architecture closest
to NapCatQQ:

```text
WeChatPadProMAX webhook/API
        |
wechatpadpromax-onebot-bridge
        |
OneBot v11 reverse WebSocket
        |
AstrBot native aiocqhttp adapter
```

Key design points:

1. AstrBot acts as OneBot v11 reverse WebSocket server, while the bridge acts as
   the protocol implementation client.

2. The bridge must maintain stable numeric IDs for OneBot compatibility because
   WeChat wxid values are not numeric. Store a durable mapping such as
   `wxid -> int64`, `chatroom wxid -> int64`, and keep original wxid in raw
   extension fields.

3. Implement the minimum useful OneBot actions first:
   `send_msg`, `send_private_msg`, `send_group_msg`, `get_msg`,
   `get_group_info`, `get_group_member_info`, `get_group_member_list`.

4. Implement `send_group_forward_msg` and `send_private_forward_msg` as fallback
   rendering because WeChatPadProMAX does not expose a confirmed generic native
   merged-forward API.

5. Centralize media caching, download, upload, duration detection, retries, and
   rate limiting in the bridge rather than inside AstrBot plugin internals.

6. Keep the AstrBot plugin as the lightweight option for simple deployments; use
   the standalone bridge for maximum OneBot ecosystem compatibility.
