# Linuxの実行環境

1. Gitと、利用するディストリビューションに対応した[Docker Engine](https://docs.docker.com/engine/install/)・[Compose plugin](https://docs.docker.com/compose/install/linux/)を導入します。
2. Docker daemonを起動し、Dockerを操作する運用アカウントを用意します。
3. 次のコマンドでバージョンとLinuxコンテナの実行環境を確認します。

```sh
git --version
docker compose version
docker info --format '{{.OSType}}'
```

最後の出力が `linux` なら[共通導入フロー](setup.md)へ進みます。Python・Node・npm・PostgreSQL clientは共通タスクのImageに含まれます。

設定・鍵・Backupはアクセスを制限したディレクトリで管理します。設定ディレクトリの権限は0700です。OSパッケージとDockerへのアクセス権はHost管理者が管理します。

## HTTPSと定期運用

Stage／ProdはLinux HostのsystemdでCaddyを動かし、別ドメインで公開します。Devはlocalhost HTTPで利用します。

- [Caddy](caddy.md)：DNS、サイト設定、証明書、reload、Rollback
- [Compose](compose.md)：環境、Image、永続Volume
- [更新](upgrade.md)：Imageの適用と切戻し
- [Backup](backup.md)：定期Job、Host外保管、復元
- [監視](monitoring.md)：ログ、閾値、障害対応

公開前に[Stage受入](stage-acceptance.md)でOAuth、Guild認可、Webhook、TLS、Transcript、監視通知、Backup Jobを確認します。
