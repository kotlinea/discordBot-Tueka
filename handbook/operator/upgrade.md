# 更新とロールバック

## Image更新

1. 対象環境の復旧セットを[Backup手順](backup.md)で取得します。対応ImageをRegistry等で保持し、暗号鍵世代も別途保管します。
2. Stageで新ImageのMigration、Health、Command、設定保存、配送、復旧を検証します。
3. 対象の`deployment.json`を検証済みImage digestへ変更します。本番はStageと同じdigestを使用します。
4. `docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build deploy up --config-dir data/environments/prod --stage-config data/environments/stage`を実行します。本番以外は`--stage-config`不要です。稼働中サービス停止→DB readiness→Migration成功→アプリ起動の順で適用します。
5. [監視](monitoring.md)でHeartbeat、HTTPエラー、Queue、DB待ちを確認します。

Schema更新は対象Imageの `migrations/postgresql/` に従います。適用状態は起動時に検査されます。

## 更新前のSnapshotへのRollback

更新前の復旧セットと、そのmanifest.jsonに記録されたImageを別Projectへ復元します。障害調査のため更新後のVolumeも保全します。

1. 新しい構成のWriterを停止し、障害調査用のDB/Volumeを保持します。
2. 更新前Snapshotと同じ環境・Discord Application・暗号鍵世代、**別Project・別ポート**の設定を用意します。ImageはSnapshotのdigest/IDに戻します。
3. [別Volume復元](backup.md)を実行します。復元CLIは元Projectにfence、復元先にpendingを記録して通常のupを抑止します。
4. Transcript/添付/DB暗号文の復号結果、Migration履歴、Queue状態を確認します。Snapshot後に成功したDiscord操作、受信したSocial Event/Ticket Messageを突合し、必要な補正を行います。
5. `docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build recovery release --config-dir data/environments/prod-recovery --reconciled`で復元先を解放し、対応Imageで起動します。本番upには復元先と同じImageで稼働するStageの確認も必要です。
6. Healthと配送を確認し、Host Caddyの転送先を新しいlocalhostポートへ切り替えます。外部callbackのOriginは維持します。元ProjectのfenceとVolumeは調査・保全のため保持します。

Snapshot以降のDB更新は復元先に存在しません。Discordのメッセージ/Role/ChannelはDB復元では巻き戻りません。既存Receiptのある配送は保持し、結果不明の処理を無条件に初回配送として再実行しないでください。照合が完了しない場合は復元先を起動せず、保留状態を維持します。

復元が失敗し元環境へ戻す場合は、復元先停止中に`docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build recovery abort --config-dir data/environments/prod-recovery --source-config data/environments/prod`を実行します。復元先は起動禁止のまま保持され、元Projectだけが解放されます。元のImage/DBが正常であることを確認してから通常のupを実行してください。

検証用Projectでの自動受入は[テスト手順](../developer/TESTING.md)、公開経路とDiscordの確認は[Stage受入](stage-acceptance.md)を参照してください。
