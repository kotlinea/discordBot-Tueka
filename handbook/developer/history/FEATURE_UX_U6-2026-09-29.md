# U6 — 表示構造・機能登録・設定操作の全体受入

対象: `9e1c6bb58961b1a472f4eff6c1ad87a8d8b6a25d` からの作業ツリー。既存U4/U5の変更とユーザーのstagingを保持。Windows / Docker Desktop Linuxコンテナで実行。状態: U0〜U6ローカル受入完了。Uの残作業なし。

## 要件と証拠の対応

| 要件 | 現行の正本・検証対象 |
| --- | --- |
| カテゴリーと大機能の分離、24機能の配置 | [architecture](../architecture.md)の配置表、Frontend RegistryのpresentationCategories、`e2e/workspaces.spec.ts` の独立した24機能対応表。概要・サーバー情報は共通入口 |
| Ticket/RRの機能内画面、既存URL・検索・戻り | 各 `.feature.tsx` のpagesと専用Router、`workspaces.spec.ts`・`routing.test.tsx`。Staffのリンクと直URLも検査 |
| 機能・カテゴリーの登録だけで拡張 | [拡張手順](../extending.md)、Backend `test_feature_extension.py` とUI `featureExtension.test.tsx`。実起動・API・Shellに仮機能を登録/解除し、専用画面overrideを確認 |
| 依存境界、認可、登録衝突・日英 | Backend/UIのfeature boundaries、feature registry、API contractテスト。共有UIから機能への依存とカテゴリー間の内部参照を拒否。UI表示はAPI認可の代替にしない |
| 設定の実態・操作統一 | `ServerInformation`、`ConfigurationState`、共有draft/save/guard、`settings-contract.spec.ts`。取得失敗・親停止・Resource消失を区別し、403/409/422で入力保持 |
| ルール再利用・一括ON/OFF | [API](../api.md)、`test_rule_operations.py`・`rule-drafts.test.ts`・`rule-operations.spec.ts`。同Trigger別対象、元ルール不変、全件原子的な状態変更、再有効化時の件数不変 |
| 共通基礎要素と機能別配置 | [CODE_MAP](../CODE_MAP.md)、[extending](../extending.md)。機能入口は個別ファイル、複数画面は機能専用フォルダー。Button/EmbedEditor/SaveBarは共有、保存は機能側 |
| 表示・Accessibility | [design](../design.md)、全Dashboardブラウザー群、日英・320/375/768/Desktopと追加414px。U0案とU2/U5の実描画比較は各段階の履歴 |
| 配布・運用・文書 | 全群ciのImage/Compose/Setup/Restore/Recovery/Caddy/Tools検査、日英Docs build・Docsブラウザー・リンク・公開境界検査 |

表示所属はRegistryへ集約され、SidebarはHubの有無で階層を切り替えない。Moderation/SocialのHubは既存URL・カテゴリー概要への導線があるため維持する。Ticket/RRの表示移動に伴うDB・Domain移設は行わない。保存Schema変更がないためMigrationは追加しない。

確定した構造・登録・状態・編集・ルール操作の契約はarchitecture、design、api、CODE_MAP、extendingへ反映した。利用者向けは日英のDashboard基本操作・保存と競合・モデレーションルールと各機能ガイドに記載した。

## 検証

入口: `docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build ci`。

全群実行 `artifacts/ci/20260929T100111-d4b3776d` はPython/Web群とImage/Runtimeまで成功し、verify-composeでexit 1となった。Migration失敗を意図的に注入した際、起動処理は現在の契約どおりValueErrorを返したが、検証スクリプトが以前のCalledProcessErrorを待っていた。`verify_compose.py` を現在の例外型と「Migration failed; application services remain stopped.」のメッセージ照合へ修正した。Writer停止・Rollback・復帰の検査は保持する。

失敗の証拠: `artifacts/verify-compose/20260929T102600-081b7689`。影響範囲の `ci --group runtime` と未実施の `ci --group secrets` を実行し、成功済みPython/Web群は繰り返さない。単一の全群実行が無失敗だったという意味ではない。

| タスク | 結果・artifact |
| --- | --- |
| test-python | 全428件成功、`artifacts/test-python/20260929T100122-11b61c83` |
| api-check | 成功、`artifacts/api-check/20260929T100500-824d3f6e` |
| commands-check | 103コマンド成功、`artifacts/commands-check/20260929T100515-3af886d0` |
| check-docs | 成功、`artifacts/check-docs/20260929T100529-594b11df` |
| verify-restore | 68表復元・設定/大きなID/キュー/参照の保持・失敗時不変更、`artifacts/verify-restore/20260929T100541-72901dfc` |
| verify-tools | Linux filesystem上の所有権・鍵保持・再実行・ポート競合成功、`artifacts/verify-tools/20260929T100644-a8654d8e` |
| typecheck | 成功、`artifacts/typecheck/20260929T100814-e179f471` |
| test-web | 全163件成功、`artifacts/test-web/20260929T100831-f50b8d8d` |
| build-web | 成功、`artifacts/build-web/20260929T100848-626d8292` |
| build-docs | 日英成功、`artifacts/build-docs/20260929T100926-345139a7` |
| test-a11y | 全164ケース成功、`artifacts/test-a11y/20260929T101045-ecbab44d` |
| test-docs-a11y | 全20ケース成功、`artifacts/test-docs-a11y/20260929T101942-705173aa`。日英ルールガイドの導線・競合案内・5画面幅を含む |
| build-image（初回） | 成功、`artifacts/build-image/20260929T102136-65157a39` |
| verify-runtime（初回） | 起動・配信・Migration・Worker・Image内Python428件成功、`artifacts/verify-runtime/20260929T102220-910e410d` |
| ci --group secrets | exit 0、61コミットで漏洩検出なし。`artifacts/ci/20260929T103043-eca6f008`、`artifacts/secrets/20260929T103050-7d96018d` |
| verify-runtime（修正後） | 起動・配信・Migration・Worker・Image内Python428件成功、`artifacts/verify-runtime/20260929T103031-aa203f0b` |
| verify-compose（修正後） | Stage/Prod分離、再起動保持、Migration失敗停止/Rollback/復帰、Dev reload/proxy成功、`artifacts/verify-compose/20260929T103433-74ca5de2` |
| verify-setup | 設定・build再実行、秘密値保持、Migrationとオフライン起動成功、`artifacts/verify-setup/20260929T104009-45d54233` |
| verify-recovery | 暗号化DB/Blob/鍵、失敗中止、Writer保留、配送照合、古いImage/Schema復帰成功、`artifacts/verify-recovery/20260929T104135-e25c189f` |
| build-image（修正後） | 成功、`artifacts/build-image/20260929T103011-0084cd8d` |
| verify-caddy | ローカルTLS・HTTPS redirect・環境分離・配信経路・内部/API文書404成功、`artifacts/verify-caddy/20260929T104531-aa365607` |
| ci --group runtime | 全項目exit 0、`artifacts/ci/20260929T103005-9e351e50` |

最終ブラウザーartifactの `workspaces-workspace-place-dff67-on-and-staff-boundaries-ja--{desktop,mobile-320}/reaction-roles-ja.png` を目視した。サーバー運営のカテゴリーとRRの内部ナビが分かれ、320pxでは内部操作と状態欄が折返し・縦配置され、操作の重なりがない。U0の配置案に沿うことを確認した。ナビの一部機能名がIDなのはFixtureの表示名によるもので、実API翻訳の検証は別のMetadata/日英テストで行う。

## 段階の記録と範囲

[U0](FEATURE_UX_U0-2026-09-25.md)で棚卸し、[U1](FEATURE_UX_U1-2026-09-25.md)で登録契約、[U2](FEATURE_UX_U2-2026-09-25.md)で配置、[U3](FEATURE_UX_U3-2026-09-25.md)で設定と共通操作、[U4](FEATURE_UX_U4-2026-09-29.md)でルールAPI、[U5](FEATURE_UX_U5-2026-09-29.md)でルールUIを受入した。

U6で確定仕様と要件対応を現行handbookと本記録へ移し、ROADMAP・実行計画・HANDOFFの参照を更新して一時 `goal.md` を削除した。終了前の計画はローカルartifact `artifacts/ci/20260929T103005-9e351e50/goal-before-close.md` に保持する。G0〜G6やU0〜U5の過去記録は書き換えない。

削除後の `check-docs` はexit 0（`artifacts/check-docs/20260929T104749-434a913b`）。作業ツリーとstagingの `git diff --check` は指摘なし。goal.mdへのMarkdownリンクが残っていないことと、上記artifactのログを確認した。検証用Composeを停止した。Commit・Stage操作は行わず、ユーザーのstagingを保持した。

ローカルの実SPA検証はHTTP fixtureを使用する。API/Transactionは専用PostgreSQL、運用検査は検証用Compose資源を使用する。実Discord・Provider・OAuth/Webhook、独立Linux Host、最新CommitのRemote CI、実Stageは別の受入であり、本作業のローカル成功では代替しない。新規業務機能・本番配布・2リポジトリ化は対象外。
