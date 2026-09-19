# 本番Image

共通Imageは、Bot・Dashboard・Social Worker・Migration・Pythonテストを同じ依存とソースで実行する。環境別ComposeとMigration後の起動順は[環境別Compose](compose.md)を参照する。実Discord/OAuth/Provider接続の確認はStageで実施する。

## ビルドと起動

Repositoryルートで `docker build -t tueka:local .` を実行する。Node stageはnpm LockからSPAとDocsを構築し、Python builderはhash付きrequirements.lockから仮想環境を構築する。RuntimeにはNode・npm・gitを導入しない。ベースImageはdigestで固定する。

起動は[導入フロー](setup.md)の各OSの完全なコマンドを使用します。アプリ設定は対象環境のapp.envのみとし、別の `docker run --env-file` 用設定ファイルは作成しません。ComposeがDB readiness→Migration→サービス起動を管理します。

| Command | 実行する処理 |
| --- | --- |
| `bot` | Discord Bot。DATA_DIRへTranscript等を保存する |
| `dashboard` | Uvicorn、0.0.0.0:8000。SPAは/ui、Docsは/docs |
| `social-worker` | Provider監視とDBへのHeartbeat |
| `migrate` | PostgreSQLの番号付きMigration、完了後終了 |
| `test` | unittest discoverによるPython全回帰 |

追加引数は対象コマンドへそのまま渡す。Dispatcherはexecで置き換わり、各サービスがPID 1となって終了Signalを受け取る。BotとWorkerは共通LifecycleでSIGTERMを受け、非同期処理をCancelしてClientとPoolを閉じる。DashboardはUvicornのSignal処理を使う。未知のCommandは終了コード2で拒否する。

## 書込み先とテスト資材

UID/GIDは10001。アプリと依存はroot所有の読取り専用ファイルで、DATA_DIRの既定値は`/data`。Botには所有者10001:10001の永続Volumeを`/data`へ接続する。Transcriptの永続化先を/tmpへ変更しない。/tmpは一時ファイル専用のtmpfsとする。read-onlyとno-new-privilegesは起動時の設定なので、Imageだけでは強制されない。

同じImageでPython回帰を行うため、tests/Fixture・Docs原稿・Frontendソースも明示的に含める。テストのPython依存は共通Lockで充足する。Nodeの単体・画面テストはDockerfile.web-testが担当し、本番Runtimeでは実行しない。

```sh
docker run --rm --read-only --cap-drop ALL --security-opt no-new-privileges:true \
  --tmpfs /tmp:rw,noexec,nosuid,size=256m --network tueka-test \
  -e TUEKA_TEST_DATABASE_URL=postgresql://user:password@postgres-test:5432/tueka_test \
  tueka:local test
```

実際の専用テスト接続先を指定する。テストはSchemaを隔離し、アプリのDBを流用しない。環境変数・DB・Backup・Transcript・ローカル仮想環境はbuild contextから除外する。

`scripts/verify_runtime_image.py --image tueka:local --network NETWORK` はHost側の`TUEKA_TEST_DATABASE_URL`とコンテナ側の`TUEKA_CONTAINER_DATABASE_URL`を使い、一時SchemaへのMigration/再適用、HTTPでのSPA/Docs/assets配信、Worker Heartbeat、権限制約、プロセス終了を確認する。専用コンテナとSchemaは終了時に削除する。Botの全Cog起動・再起動はPython回帰内のオフライン検証で確認し、Discord Login成功の証拠とは区別する。
