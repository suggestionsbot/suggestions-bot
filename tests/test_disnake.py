"""Tests library modifications to ensure changes work"""

from unittest.mock import Mock

import disnake


def test_deferred_without_send():
    a = {
        "id": "1",
        "token": "",
        "version": 1,
        "application_id": 1,
        "channel_id": 1,
        "locale": "EN_US",
        "type": 2,
    }
    inter = disnake.Interaction(data=a, state=Mock())
    assert hasattr(inter, "deferred_without_send")
    assert isinstance(inter.deferred_without_send, bool)
    assert hasattr(inter, "has_been_followed_up")
    assert isinstance(inter.has_been_followed_up, bool)
