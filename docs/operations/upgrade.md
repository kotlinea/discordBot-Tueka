# 更新とロールバック

## 更新

1. DB、Transcript、設定をバックアップします。
2. 現在のCommit IDと依存Versionを記録します。
3. 3Processを停止します。
4. Python依存を更新します。
5. `migrate_json.py`を実行します。Migrationは冪等です。
6. Dashboard FrontendとDocsを`npm ci && npm run build`で再Buildします。
7. Dashboard、Bot、Workerを起動し、Health、Command、保存、配送を確認します。

## ロールバック

Schema変更後に古いCodeへ戻す場合、Codeだけを戻さず対応するBackupからDBも復元します。ロールバック中に受信したSocial EventやTicket Messageは失われる可能性があります。

UI問題だけの場合は`DASHBOARD_UI_V2=false`でJinja UIへ戻せます。V2 Guild Allowlistを使っている場合は`DASHBOARD_UI_V2_GUILDS`も確認します。
