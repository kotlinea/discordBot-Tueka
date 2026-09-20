# Phase 3のStage受入

ローカルの隔離Compose受入は実Guild、OAuth、Provider、Registry配布、Hostの公開経路を代行しません。次の証拠を揃えてからPhase 3の運用出口を判定します。Token・Cookie・Webhook本文・秘密鍵を記録へ貼り付けないでください。

## 対象を固定する

- Stage設定ディレクトリ、Docker Host、公開Origin、テストGuild、検証担当者と時刻を記録する。
- Stage専用Discord Application/Token、OAuth callback、Provider設定を用意する。本番と混在させない。
- RegistryのImage digestと稼働する3ServiceのImage IDを記録する。Registryから同じdigestを取得して再現できることを確認する。
- S3使用時は検証専用Bucket/Prefixを用意し、対応鍵世代を秘密管理先へ保管する。

## 受入表

| Gate | 操作と確認 | 必要な証拠 |
| --- | --- | --- |
| 起動・権限 | DB readiness→Migration成功→3Service起動、非root/read-only、Volume/秘密情報の環境分離 | 構成識別情報、Image ID、health結果。秘密値なし |
| Discord | 専用GuildへBot接続、Command同期、権限不足時の診断、再起動後の応答 | 実施日時・対象機能・結果・必要なら非公開のMessage参照 |
| Host Caddy / TLS | A/AAAA・80/443到達、公開証明書と更新、HTTP→HTTPS、Stage/Prod転送先、internal/API docs 404、systemd再起動・reload・Rollback | Caddy version、証明書期限、秘匿済み検証結果。ローカル内部CA検証と区別 |
| Dashboard OAuth | 公開TLS経由でLogin/Logout、callback、CSRF、Guild所属、保存と再読込 | URLのOrigin、画面とAPI結果。query/code/tokenを記録しない |
| Webhook/Worker | 検証Providerのイベント受信、署名拒否、正常配送、重複抑止 | Eventの識別情報を必要範囲だけ記録し本文は除外 |
| 監視閾値 | 通常負荷と合意した障害注入でHTTPエラー率、Pool/lock/deadlock、Queue遅延、Heartbeatを収集 | 負荷条件、測定期間、分布、採用閾値と理由、通知到達結果 |
| 実データ復旧 | 検証Transcript/添付/Tokenの復旧セット作成、S3使用時は実オブジェクト取得、別Volumeへ復元・復号 | Snapshot時刻、Image、鍵世代指紋、復号件数、Queue照合結果 |
| Rollback | 更新前Snapshotと対応旧Imageへ別Projectで復元し、外部副作用照合後に転送先を切替 | 元/復元先Project、停止/解放記録、旧Schema/Image、Health |
| 運用継続 | Backup Timer、失敗通知、保存先権限、Host外保管、鍵/Image保持、Caddy journal管理 | Timer最終成功、通知結果、Restore実施記録 |
| 本番昇格 | 上記Stage結果と同じRegistry digestを本番へ渡し、別秘密情報で起動 | Stage/本番digest照合、変更記録、切戻し先 |

## 復旧検証の順序

1. 検証用Transcriptと添付を保存し、S3使用時はbackendと実オブジェクトの存在を確認する。
2. `scripts/recovery.py backup`でセットを取得する。実鍵や既存Objectを再生成しない。
3. 同じStage環境の別Project・未使用ポートへ`restore --source-config ...`する。元Writer停止と両側の起動抑止を確認する。
4. DB/Blob/暗号文の検証結果を確認し、Snapshot前後のDiscord Receiptと未確定処理を突合する。照合ができなければ保留を維持する。
5. `release --reconciled`後に復元先を起動し、転送先を切り替える。元Projectは停止状態を保持する。
6. 失敗時は復元先を起動せず`abort`を使う。元環境が安全に再開できることを確認してから起動する。

実行コマンド、鍵・S3の扱い、部分失敗時の制限は[Backup/Restore](backup.md)と[更新・Rollback](upgrade.md)を参照してください。今回の開発環境での結果は[進捗](../developer/PROGRESS0910.md)に記録し、この実Stage受入表の成功とは区別します。
