# 処理の軽量化と測定

日付: 2026-10-03。Windows Docker Desktop/Linuxコンテナ、Python 3.13・専用PostgreSQL 18で実施。対象は基準Commit `7d977239f74d191afe2b2210994dfdad0d42553a` からの作業ツリー差分。開始時の既存未コミット変更はなし。

## 変更と保守性

[計画](../PERFORMANCE_PLAN.md)に従い、XP加算をRETURNING付きの単一SQLへ集約し、Cogの事前/事後取得を省いた。同時更新でも自身の加算後XPを返す。クールダウンをDBより先に判定し、既存の毎分タスクで期限切れ項目を整理する。有効フラグだけの取得ではJSON解析を省く。

Dashboardは標準設定だけを一括取得する。独自factory・派生Access・別Store・専用Repositoryは既存readを使い、単件と一覧の表示変換を共有する。認可・revision・Transaction・Lease・公開API・Schema・配送/復旧の契約を維持した。新しい共有キャッシュ、汎用スケジューラー、設定スイッチは追加していない。

Live StatsはGuild IDを5秒周期で集約し、VC状態・個人へのロール付与からの不要な更新を省いた。ロール作成/削除と5分再同期を維持し、Guild単位の排他・失敗時の再保留・終了時の整理を実装した。5秒は集約待ちの周期であり、Discord制限や処理中の操作待ちは含まない。日英利用者Docsへ周期を追記した。Social履歴削除は起動/終了から1時間のmonotonic時計で管理し、失敗も次の周期へ送る。

## 変更前後の測定

同じ合成設定・XP付与量、ウォームアップ5回、測定40回で比較。値はアプリ内の処理時間であり、HTTP/Discord/Provider通信の性能ではない。比較対象の専用DBはUUID schemaで隔離し、測定終了時に削除した。時間の合否閾値は設けていない。

| 対象 | 業務SQL/Transaction（前→後） | 中央値ms（前→後） | p95 ms（前→後） |
| --- | --- | --- | --- |
| テキストXP付与 | 3→1 / 3→1 | 2.120→0.636 | 4.456→1.595 |
| Dashboard機能一覧 | 22→4 / 22→4 | 14.989→2.362 | 21.952→4.303 |

一覧は19の標準Moduleを1回にまとめ、welcome/leveling/audit_logの3つのfactoryを独立取得する。Ticket/RR専用設定は専用経路を維持する。測定Contextは設定を渡していないため、この2つの専用DB取得時間は含まない。SQL総数は接続プールの疎通確認も含めXP 6→2、一覧44→8。業務SQLとTransactionの計数はCommunity/GuildSettingsのRepositoryに限定している。

初回の測定データでSuggestion親行が不足し外部キー違反となったため合成データを修正した。接続プール確認と業務SQLの区別も修正し、変更前の最終成功値を上表へ採用した。途中の結果を最終比較には使用していない。

## 次の判断材料

稼働ジョブ10件を固定し、Suggestion Outbox完了履歴1,000/100,000件でsnapshotを計測した。変更前の中央値は2.936/15.544ms、最終測定は2.583/18.743ms。監視コードは変更しておらず、この時間差は実装の改善/悪化として扱わない。Queryは全履歴のSeq Scan、Shared Hit Blocksは15/1,429だった。変更前・初回変更後JSONのRepository限定カウンター0は未計測を表し、snapshotにTransactionがないという意味ではない。最終測定では未計測をnullと明示した。全executeのSQL総数は16だった。

次回は完了履歴を除外するWHERE条件と現行索引の利用可能性を先に評価する。メトリクスが対象とするpending/retry/processing/failed、期限切れLease、oldest due ageの一致を検証してから変更する。今回は索引・監視集計の変更を行っていない。

同期DBに`pg_sleep(0.05)`を与えたとき、5msのイベントループタイマーは変更前46.389ms、最終測定47.342ms遅延した。DB待ちがイベントループを止めることを確認した。実運用で同じ遅延がある証拠ではない。次回は実負荷のloop遅延・pool待ちを確認し、必要ならRepository操作全体を非同期境界へ移す。SQL単位のスレッド化、Transaction跨ぎ、接続層での暗黙再試行は避ける。

## 検証とローカル成果物

コマンドの共通接頭辞は `docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm`。下記引数を続けて実行した。artifactはリポジトリ内で閲覧可能だがGit未追跡のため、別checkoutへの同梱は保証しない。主要結果は本記録へ転記した。

| 引数 | 結果 | 保存先（artifacts配下） |
| --- | --- | --- |
| `--build check` | exit 0 | `check/20261003T065636-2cc0f301` |
| `-e TUEKA_PERFORMANCE_PHASE=before test-python -k performance_measurements` | exit 0、変更前の最終比較値 | `test-python/20261003T065859-41ce09a0/performance-before.json` |
| `--build -e TUEKA_PERFORMANCE_PHASE=after test-python -k performance_measurements` | exit 0、初回変更後比較値 | `test-python/20261003T070341-cbd5e8c4/performance-after.json` |
| `-e TUEKA_PERFORMANCE_PHASE=after test-python -k performance_measurements` | exit 0、最終コードの比較値 | `test-python/20261003T071858-88deb43c/performance-after.json` |
| `--build test-python` | exit 0、最終コード441件中440成功・測定1件skip | `test-python/20261003T071555-b0686ec4` |
| `test-python -k performance_contracts` | exit 0、終了処理修正後12件成功 | `test-python/20261003T071408-81fa9564` |
| `api-check` | exit 0、生成API契約一致 | `api-check/20261003T070838-b23038a6` |
| `commands-check` | exit 0、103コマンド一致 | `commands-check/20261003T070843-0dec8caa` |
| `--build test-web` | exit 0、163件成功 | `test-web/20261003T070852-ae37e654` |
| `--build check-docs` | exit 0、資料リンク・公開境界成功 | `check-docs/20261003T071447-57fb10cd` |
| `--build check-docs` | exit 0、最終測定値・完了状態・引き継ぎ更新後の検査 | `check-docs/20261003T072228-a4c9f5b7` |

終了処理テストのMockはdiscord.ext.tasksのインスタンス化で参照が変わるため修正した。実タスクを起動・cancel・awaitして、終了後に両Taskがcancel済みであることを確認した。SQL数を直接検査する受入テストも追加した。定期統計のDB一覧取得失敗後も次周期へ継続する契約を追加し、最終コードで全体回帰を再実行した。最終ログに未回収のTask例外・Tracebackはない。

`docker compose --env-file deploy/compose.env -f compose.tools.yaml down --remove-orphans` はexit 0。検証用PostgreSQLとtools Networkを削除した。`git diff --check`は成功し、新規の計画・履歴・2つのテストファイルも別途確認した。阻害要因なし。今回の範囲はローカル検証済み。

未検証: 実Discord、外部Provider、Remote CI、独立Linux Host、実Stage。配布・運用DB操作は実施していない。
