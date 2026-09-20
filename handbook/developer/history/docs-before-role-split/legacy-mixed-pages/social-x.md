---
feature_id: x_updates
title: X通知
keywords: X API Filtered Stream poll since_id 429 credits
---

# X通知

新規Postを通知します。返信とRepostは既定で除外します。

`X_BEARER_TOKEN`が必要です。運用者は`SOCIAL_X_MODE=stream`または`poll`を選択し、利用者ごとの切替は行いません。

## Stream

監視対象を`from:`条件へ集約し、Filtered Streamを1接続で管理します。切断時は指数Backoffで再接続し、保存済み`since_id`以降をTimeline APIで補完します。

## Poll

Timelineを定期確認します。Streamを維持できない契約・ネットワーク構成で使用します。429の`Retry-After`を尊重します。

APIの課金停止、Rate Limit、残Credit不足はProvider状態へ反映されます。対象だけを停止し、他Providerの監視は継続します。
