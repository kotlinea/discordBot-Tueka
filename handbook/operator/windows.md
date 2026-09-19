# Windowsの実行環境

1. Git for Windowsを導入し、新しいPowerShellで `git --version` を確認します。
2. Python 3.13を導入します。Python Launcherも選択し、`py -3.13 --version` を確認します。Launcherがない場合は `TUEKA_SETUP_PYTHON` にPython 3.13実行ファイルを指定します。
3. Host管理者が仮想化とWSL 2を有効化し、Docker Desktopを導入・起動します。Docker DesktopでLinux containersを選択します。再起動要求があれば完了してから進めます。
4. `docker info --format '{{.OSType}}'` が `linux`、`docker compose version` が成功することを確認します。接続失敗時はDocker Desktopの起動状態と実行アカウントを確認します。
5. [共通導入フロー](setup.md)のクローンと `./scripts/setup.ps1 check --config-dir data/environments/stage` から進めます。Node.jsはHostに不要です。

既存venvやDBを削除して再試行しないでください。設定ディレクトリのACLは運用者だけに許可し、バックアップの保存先も同様に保護します。

公開時はWindows FirewallとReverse Proxy/TLSを構成します。Dashboardのloopbackポートを直接インターネットへ公開しません。公開URL・OAuth・監視・Backupは[Stage受入](stage-acceptance.md)で実機確認します。
