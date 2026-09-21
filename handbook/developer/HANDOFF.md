# 作業開始

更新: 2026-09-21。現行仕様は[構成](CODE_MAP.md)と[設計](architecture.md)、実施順序・状態は[実行計画](EXECUTION_PLAN.md)を正本とする。

## 最初の手順

1. 依頼範囲と `git status --short` を確認し、既存変更を保持する。
2. [AGENTS.md](../../AGENTS.md)から作業指示を読む。[設計原則](ENGINEERING.md)に従い、責務・依存・最小の変更案を決める。
3. リポジトリルートで下記checkを実行し、対象コードとテストを読む。履歴のコマンドを作業入口にしない。
4. 変更に対応する検証を[TESTING](TESTING.md)・[TOOLS](TOOLS.md)から選ぶ。成功後の不要な繰り返しを避け、失敗や追加変更があれば再検証する。
5. 現行仕様・作業指示を更新し、実施結果を日付付きの履歴へ記録する。計画の状態は証拠がある範囲だけ更新する。

```text
git status --short
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build check
```

## 現在地と次の作業

- 追加依頼の機能中心の構造改善は[専用計画](../../goal.md)で進める。G0〜G3完了、次はG4のDashboard移行。Python/Image内各401件、API/103コマンド、Restore/ツール受入成功。[G3の範囲・証拠](history/FEATURE_STRUCTURE_G3-2026-09-21.md)を参照し、一会話につきG段階を一つ完了させる。作業記録は簡潔にする。

- Phase 0〜2、P3-1〜4、役割別Docs・導入CLIはローカル検証済み。実Stageは未準備。
- Compose基盤の最終全群検証、別Linux Hostのクリーン受入、最新CommitのRemote CI結果の確認が残る。その後Stage受入、Phase 4、Phase 5の順に進める。実害のある不具合は優先する。
- 直近のコード検証は2026-09-20のWindows Docker Desktop/Linuxコンテナ。`ci --group python`、`build-image`、`verify-runtime` が成功。Python374件、Image内374件、103コマンド、API・Docs・Restore・ツール受入を確認。[証拠と削除判定](history/UNUSED_CODE_AUDIT.md)を参照する。全群CIや独立したLinux Hostの成功を示すものではない。
- Remote CIの最新成功Run URLと実Stage受入の証拠は未確認。今回の文書整理は機能受入の追加ではない。

## 継承する判断

- 性能が同等なら最小の実装を選び、Domain間を疎結合にし、ファイル・クラスの責務を明確にする。具体的な規則は[ENGINEERING](ENGINEERING.md)。
- 利用者には一般メンバーとGuild管理者・モデレーターを含める。公開Docsは日英、運用・開発資料は日本語を正本とする。公開Docsと内部handbookの境界を保つ。
- 利用者・運用者の資料は操作と結果を紹介する。「旧ルート」「現在の実装に合わせています」「廃止しています」などの変更説明や実装者視点を使わない。コピー可能な完全コマンドを示す。
- PostgreSQLを使用する。以前の開発DBを破棄してよいという許可は、その時の開発データに限る。今後のDB・Volume・秘密値の削除許可へ拡張しない。
- app.envの一元管理、安全な不足項目補完、StageからProdへの同一Image昇格、Recoveryの明示解放を守る。[基盤作業指示](tasks/PLATFORM.md)を参照する。
- 実Host配布、DNS変更、公開証明書発行、実OAuth/Webhook、実DB操作はローカル検証に含めない。対象と依頼範囲が明確な実機作業として扱う。
- 使用も将来用途もない旧実装は削除する。動的登録・運用・復旧・明示的な将来用途を確認して判断する。

## 核心となる判断

日付、対象Commit/作業ツリー、変更理由と範囲、実行コマンド、終了結果、ログ場所、未検証事項、阻害要因、次の一手を記録する。ログには秘密値を含めない。ローカルartifactは未追跡の場合があるため、受入時は保存先と閲覧可否も確認する。過去の結果を新しいCommitの成功として扱わない。
