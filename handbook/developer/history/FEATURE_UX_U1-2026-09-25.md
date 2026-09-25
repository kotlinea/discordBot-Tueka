# U1 登録契約（完了）

対象: `e1b47e9` の作業ツリー。2026-09-25、Windows / Docker Desktop Linuxコンテナ。U0の未コミット変更を保持。U1の受入条件を完了、次はU2。U1の残作業なし。

## 実装した契約

- 既存UI Registryを拡張。表示カテゴリーの宣言と `presentationCategory` をBackendのカテゴリー・親から分離し、Shellは見出しと登録順の機能リンクを組み立てる。HubのURL・検索入口は維持。
- `screenKind` は設定/Workspace。Workspaceの `pages` に静的経路、翻訳Key、表示権限、loader、通常移動/操作入口を登録すると、内部ナビ・Route・パンくずへ接続する。操作入口は画面遷移で、保存や複製の業務処理は機能側に残す。
- 単純設定の既定画面、fields・loaderのoverride、専用設定URLを保持。別設定URLは管理者専用とし、内部ページの権限を直アクセスでもloader実行前に確認する。
- 管理者Metadataは既存 `/features` APIを独立取得。ShellのOverview取得はGuild概要だけとし、不要になった機能別 `overview` 宣言を削除。Staff・不明Guildでは管理者Metadataを取得しない。取得失敗は明示し、共通Module/Suggestions保存後はMetadataを再取得する。
- 不明な表示カテゴリー、重複ID/経路、無効な内部経路・loader・画面種別、権限の不正拡張を拒否。既存の予約経路・親循環・依存境界検査を維持し、登録文言を日英で照合する。

確定契約は [extending](../extending.md)・[architecture](../architecture.md)・[CODE_MAP](../CODE_MAP.md)へ反映。Backend/API Schema/DBは変更していない。

## 受入の対応

| U1の条件 | 証拠 |
| --- | --- |
| 単純機能の登録・共通保存 | `featureExtension.test.tsx` の実Shell。HTTP/Registryだけ差替え、保存revision・Metadata再取得・不要Overviewなしを確認 |
| 新カテゴリー・大機能の登録 | Backendと異なる表示カテゴリーへ仮Workspaceを登録。専用画面、内部ページ・操作入口・戻る・パンくず・検索・登録解除後404を確認 |
| 重複・循環・予約経路・権限 | `featureRegistry.test.ts`、`routing.test.tsx`。Staffの内部管理画面/別設定URLは404でloader未実行。管理者Metadata失敗を空表示へ変換しない |
| 既存入口・境界 | 24公開機能のID/所有カテゴリー/主URL照合、既存設定・動的詳細・Transcriptを含むRouting72件、UI依存境界検査 |
| ブラウザー | 日英、320/375/768/Desktop、既存414px補助撮影。管理者のTicket直アクセスに24機能、Overview呼出しなし。Staffは管理者Metadata/Overviewなし |

初回のDesktop/320pxスクリーンショットを目視確認。カテゴリー見出しと機能リンク、Ticket直アクセス時の一覧を確認した。大機能の最終配置・内部ナビへの適用、共通Mobile入口の縦配置はU0で定義済みのU2の範囲。仮機能はテストだけにあり、公開登録へ追加していない。

## 検証

共通入口: `docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build <task>`。通常権限のDocker接続拒否後、権限付きで実行。

| タスク | 結果 | artifacts配下の実行ID |
| --- | --- | --- |
| check | exit 0 | `check/20260925T084003-d8d9e783` |
| typecheck | exit 0 | `typecheck/20260925T085232-0f2f7f93` |
| test-web | 128件成功 | `test-web/20260925T085357-edd0e077` |
| build-web | exit 0（TypeScriptと配布build） | `build-web/20260925T085445-44d68c38` |
| test-a11y（初回） | 100件成功。最終取得分離前の検証 | `test-a11y/20260925T084851-bd0ecd98` |
| test-a11y（最終） | 最終コードで100件成功 | `test-a11y/20260925T085514-86950c84` |
| check-docs | exit 0 | `check-docs/20260925T090159-bfe1fd64` |

初回UI検査は重複カテゴリーの検証順序で期待した例外より表示カテゴリー例外が先行して1件失敗。所有カテゴリーを先に検証する順序へ修正し、再実行成功。各 `result.json`・`task.log` とブラウザーの画像はローカルartifactへ保存。

`git diff --check` は指摘なし。検証終了後にtools projectの `down --remove-orphans` を実行し、検証用ネットワークを片付けた。Volume削除・運用環境操作は行っていない。

実Discord/API・Stage、独立Linux Host、Remote CIは今回のローカル検証に含めない。次はU2の確定配置とTicket/RRへの内部ナビ適用。ルールAPI・設定操作・全体受入は計画上のU3〜U6で扱う。
