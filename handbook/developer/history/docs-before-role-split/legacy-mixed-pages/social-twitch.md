---
feature_id: twitch_updates
title: Twitch通知
keywords: Twitch EventSub stream.online stream.offline HMAC challenge
---

# Twitch通知

Twitch EventSub Webhookの`stream.online`と`stream.offline`を使用し、配信開始と終了を通知します。

`TWITCH_CLIENT_ID`、`TWITCH_CLIENT_SECRET`、公開HTTPSの`DASHBOARD_BASE_URL`、`SOCIAL_WEBHOOK_SECRET`が必要です。WorkerはApp Access Token、購読期限、失効、再登録を管理します。

WebhookはMessage ID、Timestamp、本文のHMACを検証し、Challengeへ即時応答します。古いTimestamp、不正署名、再送Message IDは拒否または重複抑止します。

配信終了時は開始通知のDiscord Messageを終了状態へ更新します。Messageが削除済み、Channelが移動済みなどで更新できない場合だけ終了通知を新規送信します。
