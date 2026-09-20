# 運用者向けガイド

システム構築、ビルド、配布、日々の保守を担当する方の資料です。Dashboardでは配信しません。Discordサーバーの機能設定は[利用者Docs](../../docs/index.md)を参照します。

1. [クローンから起動](setup.md)
2. [Discord Application](application-setup.md)・[環境変数](environment.md)
3. [管理コマンド](commands.md)
4. [Host Caddy / HTTPS](caddy.md)・[Compose](compose.md)・[Image](container.md)・[監視](monitoring.md)
5. [更新](upgrade.md)・[Backupと復元](backup.md)・[Stage受入](stage-acceptance.md)

開発者はリリース対象・Migration・契約変更とテスト結果を定義します。運用者は指定されたImageを検証・配布・起動し、監視と復旧を担当します。実機受入前のローカル成功は本番承認ではありません。
