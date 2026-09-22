# G6 最終整理・回帰（完了）

対象: `11e07e6` からの作業ツリー。2026-09-23 JST、Windows / Docker Desktop Linuxコンテナ。

- 旧Registry・集約設定モデル・Provider・平置きCog・移設前UIへの参照を点検。橋渡しImportは残っておらず、移設元の空UIフォルダーを整理した。現行 `/api/v1` と将来用途を明記したModeration Adapterは保持する。
- Image受入に24公開機能のBot/API/Worker Binding解決、移設前ソースと一時計画の非同梱検査を追加。DockerfileとDevのマウント先がカテゴリー構造を含むことも確認した。
- アプリが所有するGuild `settings` と `/servers` 配下への機能登録を拒否し、起動前の衝突テストを追加。既存URL・API・コマンドは変更していない。
- CODE_MAP、設計、拡張手順、ツール説明に現行の入口・登録・override・共有部品・同梱検証を反映した。
- ROADMAP・実行計画・HANDOFFを完了状態へ更新し、参照リンクを整理して一時ファイル `goal.md` を削除した。確定仕様は現行handbook、実施証拠はG0〜G6の履歴に保持する。

## 最終受入の対応

| 要件 | 証拠・現行仕様 |
| --- | --- |
| 機能からBackend/API/UI・所有Domainへ辿れる | [G0対応表](FEATURE_STRUCTURE_G0-2026-09-21.md)、[CODE_MAP](../CODE_MAP.md)、[設計](../architecture.md) |
| 登録で機能・カテゴリーを接続し、中央分岐を増やさない | [G5の実Bot/API/Shell受入](FEATURE_STRUCTURE_G5-2026-09-23.md)、[拡張手順](../extending.md) |
| 既定実装とoverride、業務所有境界 | [G2](FEATURE_STRUCTURE_G2-2026-09-21.md)・[G3](FEATURE_STRUCTURE_G3-2026-09-21.md)・G5。認可/CSRF/revisionは共通境界に保持 |
| 共有Button/EmbedEditorと業務保存の分離 | G2、共有UIの依存境界検査、[G4画面受入](FEATURE_STRUCTURE_G4-2026-09-23.md) |
| URL・コマンド・認可・データ・冪等性・復旧・表示 | 下記の全群CI。生成API/103コマンド、Python/UI/ブラウザー、Restore・Image・運用入口を検証 |

## 検証

実行入口: `docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build <task>`。

作業前 `check` はexit 0（`artifacts/check/20260922T161458-46e2c751`）。全群 `ci` のログは `artifacts/ci/20260922T161655-870284a7/task.log`。次の全項目を受入した。ログはローカルで閲覧確認済み。

| 群 | 結果 |
| --- | --- |
| Python | 405件、API生成物、103コマンド、文書、68テーブルのRestore、ツール受入が成功 |
| Web | 型検査、単体119件、Dashboard/Docs build、ブラウザー88件・Docs15件が成功 |
| Runtime | build-image、Image内405件、Binding/同梱/起動・終了、Compose、Setup、Recovery、Caddyが成功 |
| Secrets | 初回はG0履歴のSHA-256値22件を誤検出してexit 1。21ソースハッシュは元Commitから再計算一致、残りはOpenAPI構成ハッシュ。既存方式に従い当該Fingerprintだけを `.gitleaksignore` へ追加し、再実行は53 Commit走査・検出なしでexit 0 |

Image証拠: `artifacts/build-image/20260922T163104-59d61d76`、`artifacts/verify-runtime/20260922T163138-abb3bf54`。Secrets再実行: `artifacts/secrets/20260922T164736-759a7644`。初回CI全体の終了コードは1であり、修正後は失敗した末尾タスクだけ再実行した。成功済みのPython/Web/Runtime群を繰り返していない。

文書・一時計画整理後の `check-docs` はexit 0（`artifacts/check-docs/20260922T164957-f92e1588`）。`git diff --check` とstage済み差分の検査は指摘なし。検証専用Composeコンテナの撤去を確認し、toolsを `down --remove-orphans` で終了した。運用Volumeは変更していない。

G0〜G6の残作業なし。独立Linux Host・最新CommitのRemote CI・実Discord/OAuth/Webhook・実Stageは今回の検証に含めず、T1/C1/P3-Gで個別に受け入れる。次の作業はこれら既存ゲートの受入である。
