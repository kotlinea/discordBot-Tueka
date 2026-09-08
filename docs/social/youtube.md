---
feature_id: youtube_updates
title: YouTube通知
keywords: YouTube WebSub RSS Atom feed channel_id Uploads Playlist RSS 404 yt-dlp circuit breaker
---

# YouTube通知

新規動画とライブ開始・終了を通知します。低遅延経路はWebSub、欠落補完はRSSまたはYouTube Data APIです。

## 登録できる形式

- Channel ID：`UC`から始まるID
- Handle：`@handle`。日本語などUnicodeのHandleにも対応
- Channel URL：`https://www.youtube.com/channel/UC...`
- Handle URL：`https://www.youtube.com/@handle`
- Custom URL：`https://www.youtube.com/名前`

URLは`youtube.com`のHTTPS URLだけを受け付けます。HandleやCustom URLは公開Channel Pageを取得して正規のChannel IDへ解決します。`YOUTUBE_API_KEY`がある場合は公式APIも使用します。

## 監視経路

1. WorkerがChannel IDを確定します。
2. `https://www.youtube.com/feeds/videos.xml?channel_id=CHANNEL_ID`をWebSub TopicおよびRSS取得に使用します。
3. WebSub通知を新規イベントとして即時保存します。
4. 定期確認で欠落を補完します。
5. ライブ開始状態を確認し、終了時は開始通知Messageの更新を優先します。

::: warning RSS 404
YouTubeのRSS URLが正しいChannel IDでも一時的または継続的に404を返す場合があります。URLを書き換えて回避せず、Channel Pageを再確認します。`YOUTUBE_API_KEY`があればUploads Playlist APIへ切り替え、なければ動画一覧Pageを`yt-dlp`で補完します。
:::

公式APIの補完ではChannels APIから`contentDetails.relatedPlaylists.uploads`を取得し、Playlist Items APIで最新動画を確認します。Channel IDからUploads Playlist IDを文字列操作で推測しません。

## Circuit Breaker

RSSが繰り返し失敗した対象はRSS Circuitを開き、毎回同じ404へアクセスすることを避けます。復旧確認時に半開状態で再試行し、成功すればRSSへ戻ります。Fallback成功時も最新Cursorを更新し、同じ動画を再通知しません。

## WebSub

`DASHBOARD_BASE_URL`と`SOCIAL_WEBHOOK_SECRET`が必要です。Callbackは`/webhooks/youtube`です。購読失敗時もRSS／API監視を継続し、後で再登録します。YouTubeの更新通知を動画の新規投稿として重複配送しないよう、動画IDと保存済み状態を比較します。

## トラブルシューティング

- Handleが解決しない：公開URLをブラウザで確認し、Channel IDで再登録する
- RSSが404：Channel IDを確認し、API Key設定またはFallback状態を見る
- ReadTimeout：Workerの次回実行を待ち、連続失敗回数とCircuit状態を確認する
- 過去動画が通知された：初期Cursor作成が完了する前に対象を再作成していないか確認する
