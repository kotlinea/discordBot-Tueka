# Linuxの実行環境

1. 利用するディストリビューションの管理手順でGitを導入し、`git --version` を確認します。
2. GitとDocker Engine／Compose pluginを導入します。Python・Node・npm・PostgreSQL clientはツールImage内に固定されるためHost導入は不要です。
3. Host管理者がDocker EngineとDocker Compose pluginを導入し、Docker daemonを起動します。Dockerを操作できる運用アカウントを準備します。Docker権限の付与はHost管理者が行います。
4. `docker info --format '{{.OSType}}'` が `linux`、`docker compose version` が成功することを確認します。daemon接続・権限エラーはHost側で修正します。
5. [共通導入フロー](setup.md)のクローンと `docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build check` から進めます。Node.jsはHostに不要です。

ディストリビューションごとにパッケージ名・導入元が異なるため、スクリプトはOSパッケージを自動変更しません。設定・鍵・BackupはWeb ServerのDocument Root外へ置き、親ディレクトリの権限を0700にします。

## CaddyとTLS

Linux HostのsystemdでCaddyを動かし、Stage／Prodを別ドメインで公開します。Devはlocalhost HTTPを維持します。導入・DNS・設定生成・検証・reload・Rollbackは[Host Caddy手順](caddy.md)に集約しています。

## Registry・定期運用

Image配布は[Compose](compose.md)、更新は[更新・Rollback](upgrade.md)、定期Backup/Host外保管/復元訓練は[Backup/Restore](backup.md)、閾値・通知は[監視](monitoring.md)へ集約しています。Composeサービスと旧Host直接実行のsystemdサービスを二重起動しないでください。

公開前に[Stage受入](stage-acceptance.md)でOAuth、Guild認可、Webhook、TLS、実Transcript、監視通知とBackup Jobを検証します。ローカル自動テストの成功を実機受入の代替にはしません。
