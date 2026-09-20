# Windowsの実行環境

1. Git for Windowsを導入します。
2. 仮想化とWSL 2を有効にし、[Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/)を導入・起動します。Linux containersを選択し、再起動要求があれば完了します。
3. 新しいPowerShellで次のコマンドを実行します。

```powershell
git --version
docker compose version
docker info --format '{{.OSType}}'
```

最後の出力が `linux` なら[共通導入フロー](setup.md)へ進みます。Python・Node・npm・PostgreSQL clientは共通タスクのImageに含まれます。接続エラーが出る場合は、Docker Desktopの起動状態と実行アカウントを確認します。

設定とBackupのディレクトリは、運用者だけが参照できるACLで保護します。エラーからの再試行は、表示された対象ファイルと項目を修正して同じコマンドを実行します。

WindowsではDocker Desktopによるローカル検証を行います。Stage／ProdのHTTPS公開は[Linux HostのCaddy](caddy.md)で構成し、[Stage受入](stage-acceptance.md)で公開URL・OAuth・通知・Backupを確認します。
