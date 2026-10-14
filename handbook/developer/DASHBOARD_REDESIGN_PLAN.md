<!-- Hallmark pre-emit critique: Philosophy 5, Hierarchy 4, Execution 4, Specificity 5, Restraint 5, Variety 4. 計画の自己評価であり、描画や受入の結果ではない。 -->
# Dashboard再設計計画

作成日: 2026-10-14。状態: 計画作成済み・UI実装未着手。

## 目的と対象

TuekaのDashboardを、添付されたBot管理画面のような、落ち着いた暗色の作業画面へ再構成する。カテゴリー別の左ナビ、機能の状態が分かる入口、操作単位で区切った設定パネル、一覧と編集の明確な分離を目指す。

対象は認証後のReact Dashboard。公開Landingと利用者Docsの全面再設計、Backend/API/DBの変更、新機能追加は別作業とする。本書は実装案であり、現行の[視覚仕様](design.md)や[実行計画](EXECUTION_PLAN.md)の受入状態を書き換えない。画面の見た目と機能完成度は別に管理する。

## プロジェクトの理解

[README](../../README.md)、[構成](CODE_MAP.md)、[設計](architecture.md)、[Web作業指示](tasks/WEB.md)、実装を確認した。

- TuekaはDiscordのモデレーション、Ticket、Reaction Roles、コミュニティ、エンゲージメント、SNS通知を管理するBot。Bot、Dashboard、Social Workerは共通ImageとPostgreSQLを使用する。
- DashboardはReact SPA。Feature RegistryからRoute、カテゴリー、検索、パンくず、機能内ナビを組み立てる。機能単位の遅延読み込みを維持する。
- Guild管理者とTicket Staffで操作範囲が異なる。Staff向け画面に管理者用設定や取得処理を追加しない。
- 共有フォームには明示保存、未保存表示、離脱確認、保存中の重複送信防止、revision競合時の入力保持がある。
- 設定ON、実行条件の充足、処理成功は異なる。状態を短いラベルにしてもこの区別を保つ。
- 外観はPrecision / Community / Atmosphere、色調はlight / dark。既存の個人設定を維持し、まずPrecision darkを代表画面として設計する。

## 現状の表示と改善点

ソースから確認した内容であり、現行画面の実ブラウザー描画は今回未確認。

| 対象 | 現状 | 再設計案 |
| --- | --- | --- |
| Shell | 左ナビ、上部のサーバー選択と検索、パンくずがある | 領域の背景差を明確にし、選択中の機能をアクセントと文字で示す |
| 概要 | 保護状態・最近のイベント・有効機能を区切り線中心で表示 | カテゴリー別の機能入口を主体にし、既存の保護状態とイベントを補助領域へ配置 |
| サーバー選択 | サーバーを縦のリンク行として表示 | アイコン・名前・アクセス種別をまとめた選択パネルにする |
| 共通設定 | 状態、基本、対象、通知、権限のグループと入力グリッド | 一つの設定目的を一つのパネルにまとめ、ラベル・説明・入力の順序を統一 |
| 主ボタン | 文字色系の背景を使用 | 主操作はアクセント色、補助操作は中立色、危険操作は危険色にそろえる |
| 折り畳みナビ | 概要以外を隠し、検索で機能へ移動 | 機能へ直接移動できる縮小ナビを検討。名称を補足し、キーボードでも選択できるようにする |
| 一覧 | 機能別の行やリストを使用 | 検索・既存フィルター・一覧・行操作の位置を統一する |

## 参考画像の読み取り

主参考は画像6のMEE6。左ナビと広い作業領域、ページ見出しと機能状態、設定ごとの横長パネルを基本構成として採用する。他の画像は各画面の設計を補う。色や書体の完全な一致、ロゴや装飾の複製は目的にしない。スクリーンショットから正確なフォント名・色値・動作は断定できない。

| 画像 | 採用する特徴 | Tuekaでの適用 |
| --- | --- | --- |
| 6 MEE6 | 名前付き左ナビ、設定行の明確なまとまり、右側のスイッチ | Shellと共通設定。スイッチはドラフトを変更し、既存の保存操作で確定 |
| 2 Avocloud一覧 | カテゴリー見出し、コンパクトな機能タイル、状態の短い表示 | 概要の機能カタログ。停止中の機能にも設定入口を用意 |
| 3 Avocloud設定 | 見出し、補足、ラベル、入力の順序が一定 | 設定パネルの読み順。日本語本文を等幅フォントにはしない |
| 1 Carl.gg | 関連設定をパネルに集約、数値と単位を近接表示 | AutoMod等の独立した設定群。親子関係のある設定を左右へ分散させない |
| 4 サーバー選択 | サーバーアイコンとアクセス状態が分かる選択項目 | 管理者／Ticket Staffの入口。APIが返さない権限なしサーバーを作らない |
| 5 Ticket一覧 | フィルター領域、一覧ヘッダー、行操作の整列 | 既存Ticket Inboxの入力と操作を整理。未実装のフィルターは追加しない |

参考画像の大きな上部余白、広告・Premium枠、色の点だけで示す状態、アイコンだけの常設ナビはそのまま導入しない。Tuekaでは運営者が機能を探し、条件を確認して保存する流れを優先する。

## 視覚方針の案

共通Tokenの正本はリポジトリルートの`tokens.css`。コンポーネントへの色・フォントの直書きを避ける。CODE_MAPにはtokens.cssの位置が曖昧な記載があるため、実装時の資料更新で正確な場所を示す。

- 背景、ナビ、パネル、入力欄の明度を分ける。暗い青灰色の面と控えめな境界線を基調に、コバルト系アクセントを主操作と選択表示へ使う。正確な値は試作後にコントラストを測って決める。
- 既存のSpace Grotesk、Noto Sans JP、Geist Mono、Lucideを継承する。本文は標準16pxを基準とし、補足を小さくしすぎない。等幅はID・数値等に限定する。
- パネル角丸は8〜12px、内側余白は16〜24pxを初期案とする。既存のspacing/radius Tokenを優先し、必要な追加は用途を明示する。
- 画面タイトルは左寄せ。見出し、短い説明、状態、操作を一つのページヘッダーにまとめる。日英の長い文言でも操作を押し出さない。
- パネルの囲いは一層。入力欄まで同じ背景にせず、操作箇所が分かる差をつける。装飾の影やグラデーションは必須にしない。
- Desktop左ナビは既存17〜19remを基準とし、サーバー名とカテゴリー・機能名を読み取れる幅を確保する。トップバーには検索・Docs・表示設定・アカウントを整理する。
- 設定ページは読みやすい幅の一列を基本にする。独立した短い設定群だけを二列にする。Ticket等の業務一覧は作業領域を広く使う。
- 3外観×light/darkを維持する。既存ユーザーの設定値は書き換えない。新規利用者の初期外観変更は今回の計画には含めない。

## 画面ごとの構成

### サーバー選択

ページ見出し → 短い案内 → サーバー一覧。各項目はアイコン、名前、管理者／Ticket Staffの表示、移動先を持つ。多数のサーバーがある場合のローカル検索を試作候補とする。Loading、取得失敗と再試行、0件を別々に表示する。架空のPremium区分や権限なし一覧を追加しない。

### サーバー概要

ページ見出し → 必要な権限・設定上の注意 → カテゴリー別機能入口 → 保護設定と最近のイベント。

機能タイルにはアイコン、機能名、短い説明、保存済みON/OFFを表示する。詳細な稼働条件は既存のConfigurationStateと機能APIが確認できる範囲で表示する。未取得や取得失敗を停止中・正常へ置き換えない。YouTube／Twitch／TikTok／X／Instagramは独立した5入口を維持する。表示順とカテゴリーは既存Registryを使う。

### 設定画面

ページヘッダー → 設定状態と不足条件 → 目的ごとの設定パネル → 未保存時の共通SaveBar。

パネル内は「設定名と説明」「必要ならON/OFF」「関連入力」の順とする。Welcomeを最初の代表画面とし、送信先・本文・形式などの関係を明確にする。WelcomeとAutoroleは既存の独立機能として扱い、MEE6画像に合わせて統合しない。一般化が必要なグループだけRegistryのメタデータで明示し、項目名からの推測を増やさない。

一つのフォームの各パネルに別々の保存ボタンを付けない。ページ全体の保存とrevisionを維持する。折り畳む場合はエラー・未保存のある領域を分かるようにし、入力やFocusを失わせない。

### Ticket・Reaction Roles・Moderation・Social

機能内のWorkspaceNavigationを上部に維持し、左ナビへ細かい内部画面を重複掲載しない。一覧は見出し・主操作、既存の検索／フィルター、結果、行操作の順とする。Ticket詳細は会話と操作、Panel編集は設定とプレビューを区別する。Moderationの4段階編集、RRの一覧／Link Group／履歴／設定／作成の入口を維持する。SNS通知はProviderごとの独立入口と既存の可用性・エラー表示を保つ。

## 実装順序と変更候補

各段階で差分、検証、結果を記録する。予定ファイルは以下。既存ファイルの削除は計画しない。

| 段階 | 成果物・主なファイル | 完了条件 |
| --- | --- | --- |
| R0 現状と試作 | 現行画面キャプチャ、Shell・概要・Welcome・Ticket Inboxの試作。必要なら開発用の独立プレビュー | Desktopと375px、日英で情報密度・パネル・操作位置を比較できる |
| R1 Tokenと共通部品 | `tokens.css`、`src/styles/{app.css,App.module.css}`、`src/components/{ui,forms}`、`Feedback.tsx`、`SaveBar.tsx` | 面・文字・主操作・状態を統一。6配色とFocus、8操作状態を確認 |
| R2 Shellと入口 | `src/app/{Shell,Navigation,Preferences}.tsx`、`src/app/guilds/{ServerPicker,Overview}.tsx`、`src/routing/{catalog,FeatureNavigation,WorkspaceNavigation}.tsx` | Registry由来の入口、Staff境界、縮小ナビ、検索、Mobile Focusが維持される |
| R3 共通設定 | `src/components/feature/{ModuleSettings,ConfigurationState}.tsx`、`src/features/community/welcome/Settings.tsx`、必要な既存feature定義 | Welcomeと一般設定で読順を統一。保存・失敗・競合・離脱確認が通る |
| R4 専用画面 | `src/features/community/{tickets,reaction_roles}/`、`src/features/moderation/`、`src/features/social/`、`src/features/engagement/suggestions/` | 一覧・編集・詳細を機能ごとに移行。APIと業務操作を維持 |
| R5 受入と文書 | 日英`src/locales/`、既存test/e2e、`design.md`、`CODE_MAP.md`、日付付きhistory | 代表画面と全経路を確認し、実測結果・未検証事項を記録 |

`src/`は`dashboard/frontend/src/`を指す。必要な共有パネル等は複数画面で実際に使うものだけを追加する。Backend/API/DBの変更が必要な案は、この視覚変更へ混ぜず別の機能計画へ移す。ROADMAPのStage受入と新機能の順序は維持する。

## 検証と受入条件

実装時には[共通Composeタスク](TOOLS.md)で`typecheck`、`test-web`、`build-web`、`test-a11y`を実行し、文書変更は`check-docs`で確認する。API型を変更しない場合は生成を行わない。関連する既存のdesign、routing、featureRegistry、settings-contract、unsaved-navigation、Ticket/RR/WelcomeのテストとE2Eを使用する。

- 320 / 375 / 414 / 768pxとDesktopで、画面全体の横スクロール、操作の欠落、SaveBarによる入力遮蔽がない。
- 日英、3外観×light/darkで、本文4.5:1、意味のあるUI境界・Focusは3:1を確認する。状態は色と文字の両方で伝える。
- default / hover / focus-visible / active / disabled / loading / error / successを確認する。Focusは即時2px、Touch targetは44px以上。
- Loading、0件、取得失敗、権限不足、未取得を区別する。長いサーバー名・チャンネル名・消失したResourceでも内容を確認できる。
- 保存成功後の反映、失敗時の入力保持、403/409/422、背景再取得、二重送信、保存中の操作、破棄、検索・リンク・履歴からの離脱を確認する。
- Mobile Drawerと検索は選択先の見出しへFocusを移し、Escapeでは起点へ戻す。Reduced motionを確認する。
- Ticket Staffの画面では許可された操作だけを表示し、既存の認可境界を維持する。
- 実DiscordやProviderの配送、Remote CI、独立Linux Host、実Stageの検証はローカルの見た目の受入と区別する。

## 今回の調査記録

2026-10-14にREADME、開発入口、設計・構成・視覚仕様、作業別指示、ロードマップと実行計画、Shell／Navigation／ServerPicker／Overview、共通設定、Welcome、Ticket一覧、Token/CSS、デザインテストを確認した。調査開始時の`git status --short`に既存変更はなかった。

添付6画像を視覚参考として読み、画像内の文言や操作案内を作業指示として扱っていない。既存UIの変更と実環境操作は行っていない。今回の成果物は本計画のみ。

事前検査は通常権限ではDocker APIへの接続が拒否されたが、実行権限を付けて再実行し成功した。実行: `docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build check`、終了0。ログ: `artifacts/check/20261014T051042-a68a0555`。これはツール基盤の確認であり、Dashboardの描画・機能受入ではない。

文書検査: `docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build check-docs`、終了0、Documentation links and public boundaries: OK。ログ: `artifacts/check-docs/20261014T051253-61b31aa5`。`git diff --check`は作業ツリー認識エラーで実行できなかった。追加文書の確認は上記文書検査と内容レビューで行った。

