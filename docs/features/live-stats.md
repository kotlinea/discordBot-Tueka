---
feature_id: live_stats
title: ライブ統計チャンネル
keywords: Live Stats member count voice channel template
---

# ライブ統計チャンネル

Member数などの値をVoice Channel名へ反映します。表示専用Channelを選択し、Channel名テンプレートを設定します。

参加・退出・ロールの作成や削除による表示更新は5秒ごとにまとめて行い、5分ごとに値を再確認します。

BotにManage Channelsが必要です。DiscordのChannel名更新Rate Limitに従うため、イベントごとに即座に反映されない場合があります。テンプレートを空にした場合は初期値を使用します。

機能を無効化してもChannel自体は削除せず、最後に設定されたChannel名を保持します。
