---
feature_id: infractions
title: Warnings / Infractions
keywords: Warning points 違反履歴 失効 閾値 自動処罰
---

# Warnings / Infractions

手動・自動のWarning、points、ケース、取消、失効、段階的制裁を管理します。

## pointsと閾値

Warning Actionは設定したpointsを加算し、失効期間を設定できます。閾値Actionは有効pointsが下から上へ閾値を横切った時だけ発動します。

- 複数閾値を同時に越えた場合：最高段階だけを実行
- points失効で閾値を下回った後に再び越えた場合：再発動
- 同じ閾値以上に留まったままの追加Warning：同段階を再実行しない
- 取消済みケース：有効pointsへ含めない

## 履歴

ユーザー検索から現在points、Warning数、理由、発生源、担当者、期限、取消状態、関連するModeration Eventを確認します。手動調整と取消は管理者操作として記録されます。

既存の非失効Warningは互換pointsとして表示されます。移行処理だけで制裁が発動することはありません。
