# バックアップと復元

## バックアップ対象

- SQLite DBと、存在する場合はWAL／SHM
- 暗号化Ticket Transcriptと添付
- S3 ObjectとMetadata
- `.env`の安全な別管理コピー
- Nginx、systemdなど運用設定

稼働中SQLiteを単純コピーせず、SQLite Backup APIまたは全Process停止後の整合したコピーを使用します。

## 復元

1. Bot、Dashboard、Workerを停止します。
2. 現在のDBとTranscriptを別名で保全します。
3. 同じ世代のDB、Transcript、暗号鍵を復元します。
4. `migrate_json.py`を実行します。
5. Dashboard、Bot、Workerの順に起動します。
6. Ticket Transcript復号、Social Cursor、期限Schedule、Outboxを確認します。

::: danger 暗号鍵
`TICKET_ENCRYPTION_KEY`を失うとTranscriptを復号できません。DBだけでなく、対応する鍵の世代を安全に保管してください。
:::
