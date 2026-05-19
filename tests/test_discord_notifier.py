from __future__ import annotations

from unittest.mock import Mock, patch

from notifications.discord_notifier import DiscordNotifier, DiscordNotifierConfig
from notifications.message_builder import build_price_opportunity_embed


def test_send_price_alert_batches_embeds_over_discord_limit() -> None:
    notifier = DiscordNotifier(
        DiscordNotifierConfig(webhook_url="https://discord.com/api/webhooks/test/token", max_retries=0)
    )
    embeds = [
        build_price_opportunity_embed(
            {
                "severity": "low",
                "item_name": f"Item {idx}",
                "price": 1000 + idx,
                "deviation_pct": -30.0,
                "observed_at": "2026-05-09T10:00:00Z",
                "source": "test",
            }
        )
        for idx in range(11)
    ]

    ok_response = Mock()
    ok_response.status_code = 204
    ok_response.text = ""

    with patch.object(notifier, "_do_request", return_value=ok_response) as mocked_post:
        response = notifier.send_price_alert({"source": "test"}, embeds=embeds)

    assert response.status == "ok"
    assert mocked_post.call_count == 2
    first_payload_embeds = mocked_post.call_args_list[0][0][0]["embeds"]
    second_payload_embeds = mocked_post.call_args_list[1][0][0]["embeds"]
    assert len(first_payload_embeds) == 10
    assert len(second_payload_embeds) == 1
