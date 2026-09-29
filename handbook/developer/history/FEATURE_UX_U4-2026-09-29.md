# U4 — ルール契約

対象: `9e1c6bb58961b1a472f4eff6c1ad87a8d8b6a25d` からの作業ツリー。開始時の変更なし。Windows / Docker Desktop Linuxコンテナ、専用PostgreSQL UUID Schemaで検証。

状態: U4ローカル受入完了。U4残作業なし、次はU5（ルールUI）。

## 実装と受入範囲

Family/Triggerの対応表をHTTPから `moderation/rules.py` へ移し、既存順序を維持した。初期値は既存default_ruleから生成し、未保存・無効・ID/revisionなしで返す。テンプレートの未入力項目は保存前に補う。

一括状態変更は既存CRUDと同じGuild Moduleロックを取得し、全対象のGuild/Family・revision・有効化時の設定を検査する。状態が変わる行だけrevisionを加算し、rules_revisionを一度加算して同時Commitする。変更なしの場合もrevision検査は行う。親/Family設定、内容・priority・stop_on_match・履歴は変更しない。Schema変更なし。

RouterはSession・CSRF・live管理権限と入力Schema、Domain関数は初期値と有効化Validation、RepositoryはSQL/Transactionを担当する。共有UIやFeature Registryに保存処理を追加していない。新規APIと生成型の契約は[API仕様](../api.md)へ反映。

| U4受入条件 | 証拠 |
| --- | --- |
| 同Trigger複数作成・異なる設定 | 3 FamilyでHTTP POSTし別ID・別Channelを保存。無効ドラフトからPOSTし元ルール不変も確認 |
| 再作成なしの一括ON→OFF→ON | HTTP/DBで件数・内容・順序・履歴不変、同状態再送時にrevision不変を確認 |
| 別Guild/Family・不正ID・古いrevision | 正常IDと混在させ、全DB Snapshotが不変。重複・空・201件・必須入力も拒否 |
| 認証・認可・CSRF | 既存Fixtureの比較を維持。新規2パスのみ追加を明記し、5境界ケースと実データの不変更を検査 |
| 原子的な更新 | 行UPDATE後に失敗を注入しRollback。重複一括操作と単件編集との競合を検証 |
| 選択外と一部既存ONの保持 | 変更する行だけrevision加算、選択外・既存ON・順序/後続停止の保持を検証 |
| Runtime再取得・再起動評価 | 実AutoModCogのキャッシュがrules_revisionで更新。別Repository/空キャッシュ/新Engineでも同IDと対象Channelの評価を確認 |
| テンプレート | 全21 TriggerのFamily・初期値・無効状態・Identity不在、無効組合せ404、取得前後DB不変 |

`tests/fixtures/api_v1_contract.json` は過去契約として保持する。`test_api_contract.py` は新規GET/PUTの2パスを明示追加し、既存のpath/method/operationId/parameters/認可応答比較を弱めない。

## 検証

共通入口: `docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build <task>`。すべてHost Python/Nodeを使わず実行。

| タスク | 結果・artifact |
| --- | --- |
| check | exit 0、`artifacts/check/20260929T090830-e5ebe10e` |
| test-python（初回対象） | 6件成功、`artifacts/test-python/20260929T091234-aa6a8e50` |
| test-python（全群） | 426件成功、`artifacts/test-python/20260929T091357-acdffc6f`。U4の8件と既存418件 |
| test-python -p test_rule_operations.py（最終） | 10件成功、`artifacts/test-python/20260929T091935-fcc6930a` |
| api-generate | 成功、`artifacts/api-generate/20260929T091334-9a1ed353`。差分は新規2操作 |
| api-check | 成功、`artifacts/api-check/20260929T091435-9a26bc76` |
| test-web | 160件成功、`artifacts/test-web/20260929T091609-3c665f2a` |
| typecheck | 成功、`artifacts/typecheck/20260929T091814-b5117d6c` |
| check-docs | 成功、`artifacts/check-docs/20260929T092131-c5c4dc80` |
| test-a11y dashboard.spec.ts --grep 'rule scope\|rule order' | 8件成功、`artifacts/test-a11y/20260929T091815-f7766116`。320/375/768/Desktopの既存編集・順序保存 |

全群実行後に、混在状態・選択外の保持と単件編集との競合を追加し、再起動後の実評価も強化した。最終対象10件はすべて成功。全群428件を一度に実行したという意味ではない。API・architecture・CODE_MAPとgoal/ROADMAP/実行計画/HANDOFFを更新した。

ブラウザーは既存UIの回帰であり、新規一括操作UIの受入ではない。新規操作画面はU5。実Discord処置・Provider接続、独立Linux Host・Remote CI・Stageは未検証。APIの保存成功を実行条件充足の証拠にしない。

`git diff --check` と未追跡3ファイルの空白検査は成功。上記artifactの保存先・ログを確認した。
