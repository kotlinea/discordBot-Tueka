---
feature_id: leveling
title: レベリング
keywords: XP Rank Leaderboard Voice Role reward
---

# レベリング

Text投稿とVoice滞在からXPを加算し、Rank、Leaderboard、Role Rewardを提供します。

## TextとVoice

Text通知Channelはレベルアップ通知の送信先です。Voice XPは個別に有効化し、1分あたりXP、ソロ参加、Mute中の加算方針を設定します。

Role RewardはLevelとRoleの組を最大25件まで設定できます。同じLevelを重複登録できません。BotにManage Rolesがあり、全Reward RoleよりBot Roleが上である必要があります。

## コマンド

- `/rank`：現在のText Rankを表示
- `/leaderboard`：Text XPの順位を表示
- `/vcrank`：Voice Rankを表示
- `/vcleaderboard`：Voice XPの順位を表示

Voice XPが増えない場合はVoice機能、通知Channel、ソロ／Mute設定、BotのVoice State受信状態を確認します。
