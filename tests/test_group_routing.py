from __future__ import annotations

import asyncio

from astrbot.api.platform import MessageType

from data.plugins.astrbot_plugin_wechatpadpromax.wechatpadpromax_adapter import (
    DEFAULT_CONFIG,
    WechatPadProMaxAdapter,
)


def make_adapter() -> WechatPadProMaxAdapter:
    config = {
        **DEFAULT_CONFIG,
        "authcode": "",
        "auto_register_webhook": False,
        "auto_start_heartbeat": False,
        "auto_start_sync": False,
    }
    return WechatPadProMaxAdapter(config, {}, asyncio.Queue())


def test_group_sender_prefix_sets_group_session_and_member_sender() -> None:
    adapter = make_adapter()

    abm = adapter._convert_message(
        {"Wxid": "wxid_bot", "Timestamp": 1_700_000_000},
        {
            "msgId": "msg-1",
            "msgType": 1,
            "fromUser": "12345@chatroom",
            "toUser": "wxid_bot",
            "content": "wxid_member:\nhello from group",
            "createTime": 1_700_000_000,
        },
    )

    assert abm is not None
    assert abm.type == MessageType.GROUP_MESSAGE
    assert abm.session_id == "12345@chatroom"
    assert abm.group_id == "12345@chatroom"
    assert abm.sender.user_id == "wxid_member"
    assert abm.message_str == "hello from group"
    assert abm.raw_message["_wechatpadpromax_route"] == {
        "chat_type": "group_member",
        "group_id": "12345@chatroom",
        "sender_id": "wxid_member",
        "from_user": "12345@chatroom",
        "to_user": "wxid_bot",
        "session_id": "12345@chatroom",
        "reply_target": "12345@chatroom",
    }


def test_group_id_can_come_from_to_user_or_room_field() -> None:
    adapter = make_adapter()

    abm = adapter._convert_message(
        {"Wxid": "wxid_bot"},
        {
            "msgId": "msg-2",
            "msgType": 1,
            "fromUser": "wxid_member_2",
            "toUser": "wxid_bot",
            "roomWxid": "67890@chatroom",
            "content": "hello from alternate payload",
        },
    )

    assert abm is not None
    assert abm.type == MessageType.GROUP_MESSAGE
    assert abm.session_id == "67890@chatroom"
    assert abm.group_id == "67890@chatroom"
    assert abm.sender.user_id == "wxid_member_2"
    assert abm.message_str == "hello from alternate payload"
    assert abm.raw_message["_wechatpadpromax_route"]["chat_type"] == "group_member"


def test_private_message_keeps_friend_session() -> None:
    adapter = make_adapter()

    abm = adapter._convert_message(
        {"Wxid": "wxid_bot"},
        {
            "msgId": "msg-3",
            "msgType": 1,
            "fromUser": "wxid_friend",
            "toUser": "wxid_bot",
            "content": "hello private",
        },
    )

    assert abm is not None
    assert abm.type == MessageType.FRIEND_MESSAGE
    assert abm.session_id == "wxid_friend"
    assert abm.group_id == ""
    assert abm.sender.user_id == "wxid_friend"
    assert abm.raw_message["_wechatpadpromax_route"]["chat_type"] == "friend"


def test_route_metadata_is_exposed_on_event_extra() -> None:
    adapter = make_adapter()
    abm = adapter._convert_message(
        {"Wxid": "wxid_bot"},
        {
            "msgId": "msg-4",
            "msgType": 1,
            "fromUser": "12345@chatroom",
            "toUser": "wxid_bot",
            "senderWxid": "wxid_member_4",
            "content": "hello",
        },
    )

    assert abm is not None
    asyncio.run(adapter.handle_msg(abm))
    event = adapter._event_queue.get_nowait()

    assert event.get_group_id() == "12345@chatroom"
    assert event.get_sender_id() == "wxid_member_4"
    assert event.get_extra("wechatpadpromax_group_id") == "12345@chatroom"
    assert event.get_extra("wechatpadpromax_sender_id") == "wxid_member_4"
    assert event.get_extra("wechatpadpromax_chat_type") == "group_member"
