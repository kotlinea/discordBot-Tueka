---
feature_id: youtube_updates
title: YouTube通知
keywords: YouTube WebSub RSS Atom feed channel_id Uploads Playlist RSS 404 yt-dlp circuit breaker
---

# YouTube通知

新規動画とライブ開始・終了を通知します。ライブ終了時は開始通知の更新を優先します。

## 登録

Channel ID、`@handle`、HTTPSのyoutube.com Channel/Handle/Custom URLを登録できます。UnicodeのHandleにも対応します。

## 利用と確認

対象を保存すると確認待ちになります。稼働中へ変わったことを確認してください。初回確認を基準に、それ以降の新着動画を通知します。

通知先のBot権限とRole階層を確認し、通知Roleは専用選択欄で指定します。Providerの利用可否は運用者の設定によります。

## 問題が起きたら

HandleやFeedの取得に失敗した場合は公開Channelが存在するか確認し、正しいChannel IDで登録し直します。同じ対象を何度も削除・再作成せず、状態と発生時刻を運用者へ伝えてください。
