# Dockerデプロイ

Dev／Stage／Prodの導入は[運用者の導入手順](../handbook/operator/setup.md)、日々の操作は[管理コマンド](../handbook/operator/commands.md)を使用してください。

アプリ設定の正本は各設定ディレクトリの `app.env` です。ルート `.env` は読み込みません。`app.env.example` は項目参照用であり、生成済み設定の上書きには使いません。環境別Composeがapp.envをfile secretとしてマウントします。

Host直接実行用のsystemdサービスは[履歴](../handbook/developer/history/host-services/README.md)へ移管しました。Docker導入ではインストール・起動せず、Composeと二重起動しないでください。NginxとBackup Jobは[Linux運用](../handbook/operator/linux.md)と[Backup](../handbook/operator/backup.md)を参照してください。
