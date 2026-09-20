# Dockerデプロイ

Dev／Stage／Prodの導入は[運用者の導入手順](../handbook/operator/setup.md)、日々の操作は[管理コマンド](../handbook/operator/commands.md)を使用してください。

アプリ設定は各設定ディレクトリの `app.env` で管理します。`app.env.example` をもとにconfigureが全項目を生成し、再実行時は不足キーを補完します。入力済みの値と空欄はそのまま保持します。環境別Composeがapp.envを各サービスへ渡します。

HTTPS公開はHost Caddy、定期Backupはsystemd Timerで管理します。[Linux運用](../handbook/operator/linux.md)と[Backup](../handbook/operator/backup.md)を参照してください。
