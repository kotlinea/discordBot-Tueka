# G1 機能・カテゴリー登録契約

2026-09-21。Windows Host / Docker DesktopのLinuxコンテナで検証。比較元は[G0](FEATURE_STRUCTURE_G0-2026-09-21.md)。

## 変更

- Backendの公開24機能とBot専用4機能を `features/<category>/<id>.py` に分離。型・明示Binding・カテゴリー登録・既定設定アクセスを追加し、Bot拡張/API合成を接続した。
- UIの24機能を `<id>.feature.tsx` とカテゴリーRegistryへ登録し、既定画面/override、URL、Namespace、表示権限を定義した。
- 重複・循環・不正参照・経路/コマンド衝突、Import副作用、アプリ間Context分離、Botとloaderの一度だけの初期化を検証した。
- 公開Metadata、16拡張の順序、API、103コマンドを維持。Docker同梱とDevマウント、現行開発資料を更新した。

## 検証

ログは `artifacts/<task>/<実行ID>/`。以下はすべてexit 0。

| task | 実行ID・結果 |
| --- | --- |
| check | `20260921T054741-39eb7bce` |
| test-python | `20260921T060326-84d1e04a`、390件 |
| typecheck | `20260921T060450-98997458` |
| test-web | `20260921T060337-187de690`、23件 |
| api-check | `20260921T060506-e3a72875` |
| commands-check | `20260921T060752-b4f3189f`、103件一致 |
| build-web | `20260921T060816-786c8552` |
| build-image | `20260921T060819-35923727` |
| verify-runtime | `20260921T061001-d82f5fa4`、Image内390件・起動終了・配信 |
| verify-compose | `20260921T061014-0ad05585`、Dev/Stage/Prodの検証用構成 |
| check-docs | `20260921T061241-5578f327` |

G1完了、残作業なし。`git diff --check`と追加ファイルの末尾空白検査も成功。
実Discord/OAuth/Webhook、Linux Host、Remote CIは未検証。次はG2のwelcome試験移行と共有UI部品。設定アクセスの実機能接続、他機能移設、Shellの登録駆動化はG2〜G4の範囲。
