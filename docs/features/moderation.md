---
feature_id: moderation
title: Moderation
keywords: モデレーション, Event Trigger Condition Exemption Action Case Log
---

# Moderation

Moderationでは、検知条件、対象外にするメンバーやチャンネル、検知後の処置を設定できます。検知から履歴の確認まで、次の流れで利用します。

```text
Discord Event
  → Conditions / Exemptions
  → Trigger
  → monitor または enforce
  → Actions
  → Case / Moderation Log
```

## 判定順

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

monitorでは検知結果をイベント履歴で確認できます。削除や制裁を適用する場合はenforceを選びます。新規ルールはmonitorで検証し、誤検知がないことを確認してからenforceへ切り替えます。

## 編集イベントと重複

メッセージ編集ではキーワードやURLなどの内容を再評価し、投稿数のカウントを維持します。同じイベントの再受信による重複処置は抑止されます。
