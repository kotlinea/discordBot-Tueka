# Windowsの実行環境

1. Git for Windowsを導入し、新しいPowerShellで `git --version` を確認します。
2. Host Python・Node・npm・PostgreSQLは不要です。依存は固定tools Imageへ導入します。
3. Host管理者が仮想化とWSL 2を有効化し、Docker Desktopを導入・起動します。Docker DesktopでLinux containersを選択します。再起動要求があれば完了してから進めます。
4. `docker info --format '{{.OSType}}'` が `linux`、`docker compose version` が成功することを確認します。接続失敗時はDocker Desktopの起動状態と実行アカウントを確認します。
5. [共通導入フロー](setup.md)のクローンと `docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build check` から進めます。Node.jsはHostに不要です。

既存設定やDBを削除して再試行しないでください。設定ディレクトリのACLは運用者だけに許可し、バックアップの保存先も同様に保護します。

Stage／Prodの公開はLinux HostのCaddyを使います。Windowsではローカル検証を行います。Dashboardのloopbackポートを直接インターネットへ公開しません。公開URL・OAuth・監視・Backupは[Stage受入](stage-acceptance.md)で実機確認します。
