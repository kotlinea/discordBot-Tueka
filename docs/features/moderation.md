---
feature_id: moderation
title: Moderation
keywords: モデレーション, Event Trigger Condition Exemption Action Case Log
---

# Moderation

Moderationは保護・処置・履歴・ログの共通基盤です。各機能は独立した処置を直接実行せず、次の流れを共有します。

```text
Discord Event
  → Trigger
  → Conditions / Exemptions
  → monitor または enforce
  → Actions
  → Case / Moderation Log
```

## 判定順

更新時は全Processを停止してDBを保全し、[番号付きMigration](../operations/migrations.md)を適用してください。0004は旧AutoMod表・移行判定表と旧ID列・Warningカウンタを削除します。現行Rule、Case、Point、Event、処置結果、期限付き解除、XPは保持し、V1専用データは自動変換しません。

Migration 0004 retains current moderation records and links, scheduled actions, and XP. Legacy data remains only in the pre-migration snapshot. Rolling back requires the matching application and database snapshot; restoring a database does not undo actions already performed in Discord.

旧VersionへのRollbackは対応するアプリと適用前Snapshotを復元します。Snapshot以後の更新は失われ、Discord上で既に行われた処置はDB復元だけでは取り消されません。稼働再開前に処置と期限付き解除の状態を突合してください。

1. 対象イベントとactor種別を確認
2. Moderation全体免疫を適用
3. AutoMod、Anti-Spam、Anti-Raidなど機能別免疫を適用
4. ルール別例外を適用
5. AND条件を評価
6. Triggerを評価
7. monitor／enforceを判定
8. Actionを設定順に実行

BotとWebhookは既定で除外されます。ルールで明示的に対象化した場合だけ評価します。

## 全体設定

| 設定 | 初期値 | 説明 |
| --- | --- | --- |
| 既定ログ先 | 未設定 | 機能別ログ先がない場合の送信先 |
| 免疫Role／User／Channel | なし | 全Moderationルールから除外 |
| 証跡除外Channel | なし | 本文をDBへ保存しないChannel |
| 証跡保持日数 | 30日 | 期限後にイベント本文を削除 |
| Bot／Webhook除外 | 有効 | 明示対象化されていないactorを除外 |

::: warning 免疫の範囲
全体免疫はすべての自動検知より先に適用されます。管理Roleを免疫にする場合でも、侵害時の影響を考慮して対象を最小限にしてください。
:::

## monitorとenforce

monitorは検知とイベント保存だけを行い、削除や制裁を実行しません。新規ルールはmonitorで検証し、誤検知がないことを確認してからenforceへ切り替えます。

## 編集イベントと重複

メッセージ編集ではキーワードやURLなど内容系Triggerだけを再評価し、投稿レートへ再加算しません。イベント種別、対象ID、ルールIDを使って再送を冪等化します。
