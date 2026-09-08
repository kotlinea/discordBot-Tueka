# 用語集

| 用語 | 意味 |
| --- | --- |
| Actor | Eventを発生させたUser、Bot、Webhook |
| Trigger | Ruleが対象とする検知方法 |
| Condition | Trigger前に満たす必要があるAND条件 |
| Exemption / 免疫 | 評価から除外するUser、Role、Channelなど |
| Action | 削除、Warning、Timeout、通知などの処置 |
| Case | Moderation処置の履歴単位 |
| Revision | 競合更新を検出するVersion番号 |
| Lease | 複数Process間でJobを一時的に占有する期限付き権利 |
| Outbox | 外部配送をDBへ先に保存するQueue |
| Cursor | Providerで最後に確認したEvent位置 |
| Best effort | 外部の非公式仕様に依存し、継続動作を保証できない機能 |
