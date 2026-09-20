# 通知・ソーシャル

サーバー管理者はDashboardで対象アカウントと通知Channelを登録します。通知Roleは専用の選択欄で指定してください。本文へ直接Mentionを追加しないでください。

1. Providerを選び、アカウントIDまたはHandleと通知Channelを設定します。
2. 保存直後の「確認待ち」から「稼働中」への変化を確認します。初回確認を基準に、それ以降の新着を通知します。
3. Previewでイベント別テンプレートを確認します。

既定では1サーバー・1Providerにつき10対象までです。利用可能なProviderと上限はシステム運用者の設定によります。

テンプレートでは `{account}`、`{handle}`、`{title}`、`{text}`、`{url}`、`{platform}`、`{event}`、`{published_at}`、`{thumbnail}`、`{avatar}`、`{viewer_count}` を使用できます。

Channel消失や権限不足は設定を修正してください。確認待ちや失敗が続く場合はProvider名、対象、時刻、画面の状態を運用者へ伝えてください。
