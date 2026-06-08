from __future__ import annotations

import asyncio

from astrbot.api.message_components import File, Image, Plain, Record

from data.plugins.astrbot_plugin_wechatpadpromax.wechatpadpromax_adapter import (
    DEFAULT_CONFIG,
    WechatPadProMaxAdapter,
)
from data.plugins.astrbot_plugin_wechatpadpromax.wechatpadpromax_client import (
    WechatPadProMaxClient,
)


class FakeDownloadClient:
    authcode = "test-authcode"

    def __init__(self) -> None:
        self.voice_payloads: list[dict] = []
        self.file_payloads: list[dict] = []

    async def download_voice(self, payload: dict) -> dict:
        self.voice_payloads.append(payload)
        return {"Success": True, "Data": "dm9pY2U="}

    async def download_file(self, payload: dict) -> dict:
        self.file_payloads.append(payload)
        return {"Success": True, "fileUrl": "https://example.com/doc.pdf"}


def make_adapter() -> WechatPadProMaxAdapter:
    config = {
        **DEFAULT_CONFIG,
        "authcode": "",
        "auto_register_webhook": False,
        "auto_start_heartbeat": False,
        "auto_start_sync": False,
    }
    return WechatPadProMaxAdapter(config, {}, asyncio.Queue())


def test_inbound_image_url_becomes_image_component() -> None:
    adapter = make_adapter()

    abm = asyncio.run(
        adapter._convert_message(
            {"Wxid": "wxid_bot"},
            {
                "msgId": "msg-image",
                "msgType": 3,
                "fromUser": "wxid_friend",
                "toUser": "wxid_bot",
                "content": "https://example.com/image.jpg",
            },
        ),
    )

    assert abm is not None
    assert isinstance(abm.message[0], Image)
    assert abm.message_str == "[image]"


def test_inbound_voice_download_base64_becomes_record_component() -> None:
    adapter = make_adapter()
    fake_client = FakeDownloadClient()
    adapter.client = fake_client  # type: ignore[assignment]

    abm = asyncio.run(
        adapter._convert_message(
            {"Wxid": "wxid_bot"},
            {
                "msgId": "123",
                "msgType": 34,
                "fromUser": "wxid_friend",
                "toUser": "wxid_bot",
                "voice": {"voiceurl": "buf-1", "length": 6},
            },
        ),
    )

    assert abm is not None
    assert isinstance(abm.message[0], Record)
    assert abm.message[0].file == "base64://dm9pY2U="
    assert fake_client.voice_payloads == [
        {
            "bufid": "buf-1",
            "fromUserName": "wxid_friend",
            "length": 6,
            "msgId": 123,
        },
    ]


def test_inbound_voice_missing_download_fields_falls_back_to_text() -> None:
    adapter = make_adapter()

    abm = asyncio.run(
        adapter._convert_message(
            {"Wxid": "wxid_bot"},
            {
                "msgId": "msg-voice",
                "msgType": 34,
                "fromUser": "wxid_friend",
                "toUser": "wxid_bot",
            },
        ),
    )

    assert abm is not None
    assert isinstance(abm.message[0], Plain)
    assert abm.message_str == "[voice]"


def test_inbound_app_file_download_becomes_file_component() -> None:
    adapter = make_adapter()
    fake_client = FakeDownloadClient()
    adapter.client = fake_client  # type: ignore[assignment]
    raw_xml = (
        '<msg><appmsg appid="wx-test-app"><title>doc</title><type>6</type>'
        "<appattach><totallen>42</totallen><attachid>attach-1</attachid>"
        "<fileext>pdf</fileext></appattach></appmsg></msg>"
    )

    abm = asyncio.run(
        adapter._convert_message(
            {"Wxid": "wxid_bot"},
            {
                "msgId": "msg-file",
                "msgType": 49,
                "fromUser": "wxid_friend",
                "toUser": "wxid_bot",
                "rawContent": raw_xml,
            },
        ),
    )

    assert abm is not None
    assert isinstance(abm.message[0], File)
    assert abm.message[0].name == "doc.pdf"
    assert abm.message[0].url == "https://example.com/doc.pdf"
    assert fake_client.file_payloads == [
        {
            "appID": "wx-test-app",
            "attachId": "attach-1",
            "dataLen": 42,
            "sectionLen": 42,
            "sectionStart": 0,
            "userName": "wxid_friend",
        },
    ]


def test_business_code_success_is_not_rejected() -> None:
    assert WechatPadProMaxClient._validate_business_response(
        "/Tools/DownloadVoice",
        {"Success": True, "Code": 1000, "Message": "ok"},
    ) == {"Success": True, "Code": 1000, "Message": "ok"}
