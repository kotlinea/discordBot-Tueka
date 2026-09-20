# 通知・ソーシャル

外部サービスの更新をSocial Workerが検知し、共通DBへイベントを保存し、Discord Botが購読サーバーへ配送します。

```text
Dashboard ──購読設定──> PostgreSQL
Provider ──Webhook / Stream / Poll──> Social Worker ──正規化Event──> PostgreSQL
Discord Bot ──Delivery lease──> Discord Channel
```

## 登録

必要な入力は対象アカウントID／Handleと既定通知Channelです。1サーバー・1Providerあたり既定10対象まで登録できます。上限は`SOCIAL_MAX_SUBSCRIPTIONS_PER_PROVIDER`で変更できます。

保存直後は「確認待ち」です。Workerは対象を解決して現在のCursorだけを保存し、過去投稿を通知せず「稼働中」へ変更します。

## 共通テンプレート

イベント別にTitle、Description、本文、色、画像、Thumbnail、Footerを編集できます。

`{account}`、`{handle}`、`{title}`、`{text}`、`{url}`、`{platform}`、`{event}`、`{published_at}`、`{thumbnail}`、`{avatar}`、`{viewer_count}`を使用できます。

Role Mentionはテンプレートへ直接入力せず、通知Roleとして選択します。Discord文字数とURLは保存時に検証します。

## 配送

Providerと外部Event IDと種別、SubscriptionとEventの組で重複を防ぎます。Channel消失や権限不足は恒久失敗、Discord 429／5xxは再試行として記録されます。完了履歴は30日後に削除します。
