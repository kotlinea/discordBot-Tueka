# 共通Composeタスク

前提はGitとLinuxコンテナ対応Docker／Composeです。WindowsはDocker Desktop、LinuxはローカルDocker Engineを使います。remote Docker contextは対象外です。Host Python・Node・npm・Playwright・PostgreSQLを導入しません。

リポジトリルートで実行します。Composeの補間設定には空の `deploy/compose.env` を指定します。アプリの値は環境別app.envで管理します。

```text
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build check
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build test-python
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build ci
```

## タスク一覧

| タスク | 内容・成功条件 |
| --- | --- |
| check | Linux daemon／Compose／マウント・出力権限 |
| test-python | 専用PostgreSQL、UUID schemaによるPython回帰 |
| typecheck / test-web / build-web | TypeScript／Vitest／Frontend build |
| check-docs / build-docs | 内部資料を含むリンク検査／日英Docsと公開境界 |
| test-a11y / test-docs-a11y | Playwrightによる各画面幅・keyboard・Accessibility |
| api-check / api-generate | オフラインOpenAPI・TypeScriptの検査／書き戻し |
| commands-check / commands-generate | 全登録コマンドと日英説明の検査／生成 |
| lock-python / lock-web | 固定uv／npmによるLockの更新。変更はレビュー必須 |
| dev-web / dev-docs | localhostの5173／5174で開発表示 |
| build-image | 共通Dockerfileから `tueka:tools` を構築 |
| verify-runtime / verify-compose / verify-setup | 本番Image／Dev・Stage・Prod／空設定からのオフライン導入受入 |
| verify-recovery / verify-restore / verify-caddy | 復旧／専用DBの論理Restore／内部CAのHTTPS受入 |
| verify-tools | 専用Linux filesystemで非root所有権・鍵保持・Hostポート競合を検査 |
| secrets | 全Git履歴を固定Gitleaksで検査。値をredact |
| setup / deploy / recovery | 既存CLIへ引数を委譲。helpで引数を確認 |
| ci | 全検査。`--group python / web / runtime / secrets` でCIと同じ分割 |

引数はタスク名の後ろへ追加します。`commands-generate` は既存の日英説明を保持します。登録の追加・削除時は `docs/reference/commands.json` の対応表を先に編集し、不足説明を埋めてから生成してください。

```text
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build api-generate
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build commands-check
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build deploy --help
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build ci --group runtime
```

単独のImage受入前には `build-image` を実行します。別Imageは `run -e TUEKA_TOOLS_IMAGE=tueka:ci verify-compose` の形式で指定できます。一括ciは実行ごとに専用Image tagとCompose projectを使います。

`verify-runtime` はImage内のBot/API/Worker Binding解決、移設前ソースの不在、非root/read-only、SPA/Docs配信、Migration・Worker起動終了とPython全件を確認します。実Discordへのログインや運用DBへの接続は行いません。

## 開発サーバー

```text
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build --service-ports dev-web
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build --service-ports dev-docs
```

それぞれ別ターミナルで実行します。終了はCtrl+Cです。dev-web単体はUI開発向けです。Bot・DB・APIを含む開発は[Dev導入](../operator/setup.md)で起動してください。

## 依存と出力

`Dockerfile.tools` はPython／Node／Docker CLI・Compose／uv／Playwrightのdigestを固定します。Pythonはhash付きrequirements.lock、npmは各package-lockを使用し、Playwright ImageとLockのバージョンが異なる場合はbuildで拒否します。依存変更後は `--build` でImageを再構築します。Hostのnode_modulesやvenvは読みません。

検査は作業コピーで実行し、追跡ファイルを変更しません。結果・ログ・HTML・traceは `artifacts/<task>/<実行ID>/` に保存します。生成・Lock更新だけが指定ファイルを書き戻します。テスト用PostgreSQLはHostへポートを公開しません。

単独タスク後のテスト基盤停止:

```text
docker compose --env-file deploy/compose.env -f compose.tools.yaml down --remove-orphans
```

これはtools projectだけを停止します。Dev／Stage／ProdのVolumeを削除しません。受入が作るUUID付きprojectは各受入のfinallyで片付けます。強制終了・Host停止の場合は、残存project名を確認して検証用資源だけを片付けてください。

## Docker権限とパス

通常の検査・生成・secretsタスクにDocker socketはありません。secretsはネットワークも無効にします。check、Image構築、運用・Docker受入、ciはHost Dockerを操作できるため、信頼するリポジトリのコードだけで実行します。

設定・Backupの標準保存先はリポジトリ配下のdataです。外部ディレクトリは追加bind mountで明示します。例えばLinux Hostの既存設定を読む場合:

```text
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build -v /srv/tueka-config:/external/config deploy status --config-dir /external/config/stage
```

Windowsでも `-v "D:/Tueka config:/external/config"` を同じ位置に指定できます。指定する `--config-dir` はコンテナ側パスです。管理タスクは自身のMountsからdaemon側のパスを求め、子Composeのbind／secretを変換します。Hostのパスを推測・固定しません。見えないパスは処理前に修正方法を表示して拒否します。

Git submodule／worktreeで.gitが外部への参照になっている場合、secretsタスクには参照先の追加mountが必要です。標準受入は通常のcloneを使います。

エラー内の `/workspace/` はリポジトリルートに対応します。追加mountの場合は指定したコンテナ側パスを使います。

## 証拠の扱い

Linuxコンテナでの成功とLinux Host受入は区別します。WindowsはDocker Desktopで受入し、Remote CIはRun URLとCommitを記録します。実StageのDNS・OAuth・Webhook・公開証明書・systemd・実S3はこのローカル基盤の成功では完了扱いにしません。

## Private Registry

Hostのcredential helperをLinuxコンテナへコピーしません。Private Registryを使う場合は、運用者が専用のDocker設定Volumeへ明示的にloginします。次のREGISTRYを実際のRegistry名へ置き換え、対話入力してください。パスワードを引数へ書きません。

```text
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --entrypoint docker -v tueka-registry:/root/.docker deploy login REGISTRY
```

pull／buildを伴う運用タスクにも同じ `-v tueka-registry:/root/.docker` をrunオプションとして付けます。これはRegistry認証だけの保存先で、アプリの設定元はapp.envのままです。VolumeへのアクセスはDocker管理権限に準じます。CIの公開Image検証にはこのVolumeを渡しません。
