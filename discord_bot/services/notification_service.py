# services/notification_service.py
# Why: Discord API 経由のDM送信は副作用を伴うI/O処理のため services/ に配置。
#      旧 routes/survey.py の send_dm_notification を移動。
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class NotificationService:
    """Discord DM 通知の送信サービス。

    設計原則:
    - ステートレス: @staticmethod で実装
    - ctx 非依存: bot_token, user_id 等のプリミティブ型を引数に取る
    """

    @staticmethod
    async def send_dm(
        bot_token: str,
        user_id: str,
        survey_title: str,
        survey_id: int,
        dashboard_base_url: str = "http://dashboard.awajiempire.net",
    ) -> bool:
        """ユーザーにDMでアンケート回答確認と編集リンクを送信する。

        Args:
            bot_token: Discord Bot のトークン
            user_id: 送信先ユーザーのDiscord ID
            survey_title: アンケートタイトル
            survey_id: アンケートID
            dashboard_base_url: ダッシュボードのベースURL
        Returns:
            DM送信が成功したかどうか
        """
        if not bot_token:
            logger.warning("Bot token missing, cannot send DM.")
            return False

        headers = {
            "Authorization": f"Bot {bot_token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                # 1. DMチャンネルを作成/取得
                dm_channel_url = "https://discord.com/api/v10/users/@me/channels"
                r = await client.post(
                    dm_channel_url,
                    json={"recipient_id": user_id},
                    headers=headers,
                )
                if r.status_code not in (200, 201):
                    logger.warning("Failed to create DM channel: %s", r.text)
                    return False

                channel_id = r.json().get("id")

                # 2. メッセージ送信
                msg_url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
                edit_url = f"{dashboard_base_url}/form/{survey_id}"

                content = (
                    f"**アンケート回答ありがとうございます**\n"
                    f"「{survey_title}」への回答を受け付けました。\n\n"
                    f"**回答の修正はこちらから:**\n{edit_url}\n"
                )

                r_msg = await client.post(
                    msg_url,
                    json={"content": content},
                    headers=headers,
                )
                if r_msg.status_code in (200, 201):
                    return True
                else:
                    logger.warning("Failed to send DM: %s", r_msg.text)
                    return False

            except httpx.TimeoutException:
                logger.error("DM send timed out for user %s", user_id)
                return False
            except Exception as e:
                logger.error("Exception in send_dm: %s", e)
                return False
