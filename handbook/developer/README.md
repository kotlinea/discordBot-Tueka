# 開発者向けガイド

コード修正・設計・検証・リリース対象定義を担当する人向けの資料です。まず[作業開始と引き継ぎ](HANDOFF.md)を読み、[AGENTS.md](../../AGENTS.md)から作業別指示を選んでください。

| 調べる内容 | 正本 |
| --- | --- |
| 設計判断・責務・疎結合 | [エンジニアリング原則](ENGINEERING.md) |
| ファイル構成・実装入口 | [構成表](CODE_MAP.md) |
| 現行の処理契約 | [アーキテクチャ](architecture.md)・[API](api.md)・[視覚仕様](design.md) |
| Bot・Domain・DBの変更 | [Backend作業指示](tasks/BACKEND.md)・[機能追加](extending.md) |
| API・画面の変更 | [Web作業指示](tasks/WEB.md) |
| 設定・Docker・運用基盤の変更 | [基盤作業指示](tasks/PLATFORM.md) |
| 文書の執筆・検査 | [編集基準](DOCUMENTATION.md) |
| 実行・検証 | [共通Composeタスク](TOOLS.md)・[テスト](TESTING.md) |
| 作業順序・受入状態 | [実行計画](EXECUTION_PLAN.md)・[ROADMAP](../../ROADMAP.md) |
| 運用者への受渡し | [運用者ガイド](../operator/README.md) |
| 過去の判断・証拠 | [履歴](history/README.md) |

現行資料は実装と同じ変更で更新し、予定と実装済みを区別します。記録時点の状況は履歴に保存します。内部資料は公開Docsのビルド元に含めません。
