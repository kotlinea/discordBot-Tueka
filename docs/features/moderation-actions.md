---
feature_id: moderation_actions
title: Moderation Actions
keywords: Warn Timeout Kick Ban Unban Softban Purge Lock Lockdown
---

# Moderation Actions

手動コマンドと自動ルールは同じModeration Serviceを使用し、権限検証、ケース作成、DM、ログを共通化します。

## 利用できる処置

Warn、Timeout、Timeout解除、Kick、Ban、Unban、Tempban、Softban、メッセージ削除、最近のメッセージ削除、リアクション削除、チャンネル Lock／Unlock、Server Lockdown／解除を利用できます。

影響が大きいBanやLockdownは、ダッシュボードに表示された対象ユーザーIDまたはサーバーIDを入力して確認します。処置の実行直前に権限、ロール階層、対象の状態を確認し直します。

ダッシュボードのTimeoutは1分〜28日、Lockdownは1分〜24時間で指定します。Banは自動解除されません。サーバー所有者やAdministrator権限を持つメンバーのTimeoutは変更できません。

## Discordコマンド

処置は`/mod`グループから実行できます。`/warn`、`/timeout`、`/kick`、`/ban`、`/clear`からも対応する処置を実行できます。引数と必要権限は[コマンド一覧](../reference/commands.md)を確認してください。

SoftbanはBan後にUnbanします。前半だけ成功した場合もAction結果へ記録されるため、ケースとログを確認して手動復旧してください。
