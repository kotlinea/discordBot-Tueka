---
feature_id: moderation_actions
title: Moderation Actions
keywords: Warn Timeout Kick Ban Unban Softban Purge Lock Lockdown
---

# Moderation Actions

手動コマンドと自動ルールは同じModeration Serviceを使用し、権限検証、ケース作成、DM、ログを共通化します。

## 利用できる処置

Warn、Timeout、Timeout解除、Kick、Ban、Unban、Tempban、Softban、メッセージ削除、最近のメッセージ削除、リアクション削除、Channel Lock／Unlock、Server Lockdown／解除を利用できます。

高い影響を持つBanやLockdownは、ダッシュボードで対象名を入力して確認します。Action実行直前に権限、Role階層、対象状態を再検証します。

## Discordコマンド

処置は`/mod`グループから実行できます。`/warn`、`/timeout`、`/kick`、`/ban`、`/clear`からも対応する処置を実行できます。引数と必要権限は[コマンド一覧](../reference/commands.md)を確認してください。

SoftbanはBan後にUnbanします。前半だけ成功した場合もAction結果へ記録されるため、ケースとログを確認して手動復旧してください。
