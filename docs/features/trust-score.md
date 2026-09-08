---
feature_id: trust_score
title: Trust Score
keywords: 信頼度スコア 違反履歴 retention threshold
---

# Trust Score

Moderationケースと違反履歴から管理者向けの参考値を表示します。一般Memberへ公開する評価や、単独で自動処罰を決定する仕組みではありません。

| 設定 | 範囲 | 説明 |
| --- | --- | --- |
| 保持日数 | 1～3650日 | 算出対象に残す履歴期間 |
| フラグ閾値 | 0～100 | 管理者画面で確認対象として表示する境界 |

履歴の取消や失効は再計算へ反映されます。自動処罰はTrust Scoreではなく、[Warnings / Infractions](./infractions)のpoints閾値で設定してください。
