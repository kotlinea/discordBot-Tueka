---
feature_id: instagram_updates
title: Instagram通知
keywords: Instagram RSS Professional OAuth best effort ETag Last-Modified
---

# Instagram通知

本人連携済みProfessional Accountの情報を保持し、任意公開アカウント監視には運用者設定の外部RSS Adapterを使用します。

外部RSSを使う場合は`INSTAGRAM_RSS_URL_TEMPLATE`を設定します。WorkerはテンプレートからだけURLを生成し、Dashboard利用者に任意URLを入力させません。固定HostとRedirect先を検証し、ETagとLast-Modifiedを利用します。

::: warning ベストエフォート
外部RSS Adapterは非公式です。未設定時は公開アカウントの登録画面を利用不可にします。RSS認証値は`INSTAGRAM_RSS_AUTH_TOKEN`で管理し、画面やログへ表示しません。
:::

確認間隔は既定120秒です。Adapter障害時もYouTube、Twitch、X、TikTokの処理を停止しません。
