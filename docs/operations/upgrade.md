# 更新とロールバック

## 更新

1. DB、Transcript、設定をバックアップします。
2. 現在のCommit IDと依存Versionを記録します。
3. 3Processを停止します。
4. Python依存を更新します。
5. [番号付きMigration](./migrations.md)を適用します。0002から旧Ticket表の削除を含むため、事前に複製DBで検証します。
6. Dashboard FrontendとDocsを`npm ci && npm run build`で再Buildします。
7. Dashboard、Bot、Workerを起動し、Health、Command、保存、配送を確認します。

## ロールバック

Schema変更後に古いCodeへ戻す場合、Codeだけを戻さず対応するBackupからDBも復元します。ロールバック中に受信したSocial EventやTicket Messageは失われる可能性があります。

管理画面の問題は、検証済みFrontend資産と対応するアプリVersionを復元して対処します。Jinja管理画面への切替はありません。
