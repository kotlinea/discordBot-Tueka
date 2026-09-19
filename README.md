# Tueka

Discordのモデレーション、チケット、リアクションロール、コミュニティ機能、SNS通知をDashboardで管理するBotです。

| あなたの役割 | 最初に読む資料 |
| --- | --- |
| 一般メンバー・サーバー管理者・モデレーター | [利用者Docs](docs/index.md) / [English](docs/en/index.md)。公開環境では `/docs/` |
| システム構築・保守担当 | [運用者ガイド](handbook/operator/README.md)：クローン、設定、build、起動、監視、復旧 |
| コード修正・リリース担当 | [開発者ガイド](handbook/developer/README.md)：設計、テスト、実行計画、進捗 |

本番ImageはBot/Dashboard/Social Worker/Migrationで共用し、PostgreSQLへ接続します。導入の正本は[Windows/Linuxの導入フロー](handbook/operator/setup.md)です。Hostへの直接起動は開発・既存環境向けの補助手順です。

開発順序は[ROADMAP](ROADMAP.md)と[現行実行計画](handbook/developer/EXECUTION_PLAN.md)を参照してください。運用・開発資料は公開Docsおよび本番Imageに含めません。

資格情報、DB、暗号鍵、Transcript、Backupは公開ディレクトリやGitへ置かないでください。Swagger UI/OpenAPIは明示的に有効化したDevだけで公開します。
