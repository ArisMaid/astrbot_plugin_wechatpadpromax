from __future__ import annotations

import asyncio

from astrbot.api.event import MessageChain
from astrbot.api.message_components import Image, Node, Nodes, Plain, Record

from data.plugins.astrbot_plugin_wechatpadpromax.wechatpadpromax_client import (
    WechatPadProMaxClient,
)
from data.plugins.astrbot_plugin_wechatpadpromax.wechatpadpromax_sender import (
    WechatPadProMaxMessageSender,
)


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def send_text(self, to_wxid: str, content: str, at: str = "") -> dict:
        self.calls.append(("text", {"to": to_wxid, "content": content, "at": at}))
        return {"Success": True}

    async def send_image_base64(self, to_wxid: str, image_base64: str) -> dict:
        self.calls.append(("image", {"to": to_wxid, "base64": image_base64}))
        return {"Success": True}

    async def send_voice_base64(
        self,
        to_wxid: str,
        voice_base64: str,
        voice_type: int = 3,
        voice_time: int = 0,
    ) -> dict:
        self.calls.append(
            (
                "voice",
                {
                    "to": to_wxid,
                    "base64": voice_base64,
                    "type": voice_type,
                    "time": voice_time,
                },
            ),
        )
        return {"Success": True}

    async def send_video_base64(
        self,
        to_wxid: str,
        video_base64: str,
        image_base64: str = "",
        play_length: int = 0,
    ) -> dict:
        self.calls.append(
            (
                "video",
                {
                    "to": to_wxid,
                    "base64": video_base64,
                    "cover": image_base64,
                    "length": play_length,
                },
            ),
        )
        return {"Success": True}


def test_sender_preserves_text_image_order() -> None:
    client = FakeClient()
    sender = WechatPadProMaxMessageSender(client)  # type: ignore[arg-type]
    chain = MessageChain(
        [
            Plain("before"),
            Image.fromBase64("aW1hZ2U="),
            Plain("after"),
        ],
    )

    asyncio.run(sender.send_chain("wxid_target", chain))

    assert [name for name, _ in client.calls] == ["text", "image", "text"]
    assert client.calls[0][1]["content"] == "before"
    assert client.calls[1][1]["base64"] == "aW1hZ2U="
    assert client.calls[2][1]["content"] == "after"


def test_sender_sends_record_as_voice() -> None:
    client = FakeClient()
    sender = WechatPadProMaxMessageSender(client)  # type: ignore[arg-type]
    chain = MessageChain([Record.fromBase64("dm9pY2U=")])

    asyncio.run(sender.send_chain("wxid_target", chain))

    assert [name for name, _ in client.calls] == ["voice"]
    assert client.calls[0][1]["base64"] == "dm9pY2U="
    assert client.calls[0][1]["type"] == 3


def test_sender_falls_back_merged_forward_to_text() -> None:
    client = FakeClient()
    sender = WechatPadProMaxMessageSender(client)  # type: ignore[arg-type]
    node = Node(name="Alice", uin="wxid_alice", content=[Plain("hello")])
    chain = MessageChain([Nodes([node])])

    asyncio.run(sender.send_chain("wxid_target", chain))

    assert [name for name, _ in client.calls] == ["text"]
    assert "[merged forward]" in client.calls[0][1]["content"]
    assert "Alice: hello" in client.calls[0][1]["content"]


def test_business_response_validation_rejects_explicit_failure() -> None:
    try:
        WechatPadProMaxClient._validate_business_response(
            "/Msg/UploadImg",
            {"Success": False, "Message": "upload failed"},
        )
    except RuntimeError as e:
        assert "upload failed" in str(e)
    else:
        raise AssertionError("expected RuntimeError")
