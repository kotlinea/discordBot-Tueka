# アプリImage

Bot、Dashboard、Social Worker、Migrationは共通のアプリImageを使用します。Stageで受入したImageをProdへ配布します。

## ビルド

リポジトリルートから次を実行すると、アプリ・ダッシュボード・日英Docsを含む `tueka:tools` を構築します。

```text
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build build-image
```

環境の設定から起動まで進める場合は、[導入フロー](setup.md)のconfigure・build・startを使用します。buildの結果は対象環境のdeployment.jsonへImage IDとして記録されます。別Hostへの配布にはRegistryのdigest参照を使用します。

## サービス

| サービス | 処理 | 確認方法 |
| --- | --- | --- |
| bot | Discordのコマンドとイベントを処理 | Discordで `/ping`、healthのBot状態 |
| dashboard | 管理画面とAPI、`/docs/`を配信 | 公開URLとhealth |
| social-worker | SNSの更新を取得 | Heartbeatと通知対象の状態 |
| migrate | PostgreSQLのSchemaを更新して終了 | 起動時のMigration結果 |

起動・停止・更新には[管理コマンド](commands.md)を使用します。起動順はDB readiness、Migration、アプリサービスです。

## データと権限

アプリはUID/GID 10001で動作します。Composeはアプリのファイル領域を読取り専用にし、Transcript用Volumeを `/data`、一時領域を `/tmp` へ接続します。BotはTranscriptを書き込み、Dashboardは閲覧用に読み取ります。DBは専用のPostgreSQL Volumeへ保存されます。

設定は環境別app.envで管理します。永続化・環境分離の詳細は[Compose](compose.md)、データの保全は[Backup](backup.md)を参照してください。

## 配布前の確認

[Stage受入](stage-acceptance.md)でDiscord、OAuth、通知、Docs、復旧を確認します。Imageと専用DBによる自動検証は[テスト手順](../developer/TESTING.md)を参照してください。
