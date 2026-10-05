---
feature_id: anti_raid
title: Anti-Raid
keywords: Join Raid 大量参加 大量退出 新規アカウント Lockdown
---

# Anti-Raid

短時間の参加・退出、新規アカウント比率、参加直後の行動からRaid状態を検知します。

## Triggerと状態

- `join_rate`：時間窓内の参加数
- `leave_rate`：時間窓内の退出数
- `new_account_ratio`：参加者に占める作成直後アカウントの割合
- `new_member_activity`：参加直後の投稿など

Raidの発生状況と対応状態を確認できます。開始後は継続条件を評価し、解除条件または管理者操作で終了します。Botの再起動後も状態を復旧します。

## Action

管理者通知、対象メンバーへのTimeout／Kick／Ban、チャンネル Lock、Server Lockdownを組み合わせられます。Lockdownは変更前Overwriteを保存し、期限または手動操作で解除します。

Lockdown後に管理者がOverwriteを変更した場合は、自動解除で上書き復元せず競合としてログへ残します。

::: warning 必要権限
LockdownにはManage Channels、制裁にはModerate Members、Kick Members、Ban Membersが必要です。実行時のロール階層も満たす必要があります。
:::

ルールの作成・複製・一括ON/OFFは[ルール操作ガイド](../dashboard/moderation-rules.md)を参照してください。
