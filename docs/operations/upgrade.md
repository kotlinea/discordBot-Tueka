# 更新とロールバック

## Image更新

1. 対象環境の復旧セットを[Backup手順](./backup)で取得します。対応ImageをRegistry等で保持し、暗号鍵世代も別途保管します。
2. Stageで新ImageのMigration、Health、Command、設定保存、配送、復旧を検証します。
3. 対象の`deployment.json`を検証済みImage digestへ変更します。本番はStageと同じdigestを使用します。
4. `python scripts/deploy.py up --config-dir <対象設定> --stage-config <Stage設定>`を実行します。本番以外は`--stage-config`不要です。旧Writer停止→DB readiness→Migration成功→アプリ起動の順で適用します。
5. [監視](./monitoring)でHeartbeat、HTTPエラー、Queue、DB待ちを確認します。

旧SQLiteのMigration番号をPostgreSQLへ当てはめないでください。PostgreSQLの適用履歴は`migrations/postgresql/`です。適用済みファイルは変更せず、追加Migrationを使います。

## Snapshotと旧ImageへのRollback

Codeだけを戻さず、更新前の復旧セットとその`manifest.json`に記録されたImageを使います。破壊的な逆Migrationや既存Volumeの上書きは行いません。

1. 新しい構成のWriterを停止し、障害調査用のDB/Volumeを保持します。
2. 更新前Snapshotと同じ環境・Discord Application・暗号鍵世代、**別Project・別ポート**の設定を用意します。ImageはSnapshotのdigest/IDに戻します。
3. [別Volume復元](./backup)を実行します。復元CLIは元Projectにfence、復元先にpendingを記録して通常のupを抑止します。
4. Transcript/添付/DB暗号文の復号結果、Migration履歴、Queue状態を確認します。Snapshot後に成功したDiscord操作、受信したSocial Event/Ticket Messageを突合し、必要な補正を行います。
5. `recovery.py release --reconciled`で復元先を解放し、対応Imageで起動します。本番upには同じ旧Imageで稼働するStageの確認も必要です。
6. Healthと配送を確認し、Host Nginxの転送先を新しいlocalhostポートへ切り替えます。外部callbackのOriginは維持します。元ProjectのfenceとVolumeは調査・保全のため保持します。

Snapshot以降のDB更新は復元先に存在しません。Discordのメッセージ/Role/ChannelはDB復元では巻き戻りません。既存Receiptのある配送は保持し、結果不明の処理を無条件に初回配送として再実行しないでください。照合が完了しない場合は復元先を起動せず、保留状態を維持します。

復元が失敗し元環境へ戻す場合は、復元先停止中に`recovery.py abort --config-dir <復元先> --source-config <元設定>`を実行します。復元先は起動禁止のまま保持され、元Projectだけが解放されます。元のImage/DBが正常であることを確認してから通常のupを実行してください。

ローカル受入は`python scripts/verify_recovery.py --image <検証Image>`です。専用Projectで旧Image/SchemaのSnapshot取得、新Image/Schemaへの更新、別Volumeで旧Image/Schemaへの復元、暗号文復号、Receiptを照合する保留配送の再開を検証します。実GuildやHost Nginxの切替を自動実行するものではありません。
