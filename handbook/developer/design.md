# Dashboardの視覚仕様

共通Tokenの正本は `tokens.css`。ページ固有の色・フォントを直接追加せず、既存Tokenとコンポーネントを使う。以下は画面変更時に維持する設計基準であり、全画面の受入済みを意味しない。

## 構成

- 操作領域とナビゲーションを分けたWorkbench構成。Desktopはサイドナビゲーション、Mobileはトップバーと全高のナビゲーションを使う。
- 外観はPrecision / Community / Atmosphere、色調はlight / dark。
- 見出しはSpace Grotesk、本文はNoto Sans JP、識別子はGeist Mono。IconはLucide。
- 認証後の画面はReact SPA。起動前にFrontendをbuildする。

## 操作・表示の基準

- 共通入口は概要とサーバー情報。サーバー運営にTicket/RRを配置し、コミュニティ・エンゲージメント・モデレーション・通知とソーシャルは同じ形式のカテゴリー見出しと機能リンクを使う。
- 大機能の内部ナビは機能画面の上部に置く。Ticketの受付設定は下位ナビへまとめ、概要のリンク集を重複させない。RRの一覧・Link Group・履歴・設定・作成を独立した入口にする。
- Mobileナビは縦一列に配置する。選択後はDrawerを閉じ、遅延読み込み先の主見出しへFocusを移す。検索結果の選択も同じ動作とし、Escapeで閉じる場合は起点へ戻す。

- 更新は明示的な保存または確認操作で確定する。ルール編集は保存まで編集中として扱う。Ban・Lockdownは入力確認を要求する。
- 設定の保存値と稼働条件を分ける。未取得は不明、取得失敗は再試行付きのエラーとし、0件・無効・正常に置き換えない。参照できない選択済みResourceはID付きで残す。
- 編集中は未保存表示・保存・破棄を揃え、保存中は入力と重複送信を抑止する。背景再取得・403/409/422で入力を上書きしない。リンク・検索・ブラウザー履歴からの離脱も未保存確認の対象とする。ダイアログの閉じるは確認、明示的な破棄は再確認なしで扱う。
- MotionはOverlayと状態変化の説明に用い、120〜240msを基準とする。Reduced motionでは空間移動を抑え、Opacity変化は150ms以内にする。
- Focusは2pxで即時表示し、アニメーションしない。Touch targetは44px以上とする。
- Mobile-firstで320 / 375 / 414 / 768pxを確認し、Content breakpointは40 / 60 / 90remを使う。
- 領域ごとの囲いは一層にし、Cardの入れ子や均等な3枚Cardの機能説明を避ける。
- Moderationルール編集は4段階の操作として構成する。

## 文言と権限

- 日本語は簡潔で丁寧にし、英語も同等の情報を提供する。Labelは対象、Buttonは具体的な動作、Errorは原因と復帰方法を示す。
- 実測していない指標、利用者の声、保護効果、Discordの状態を創作しない。
- Lockdown/Channel lockはManage Channels、Reaction削除/PurgeはManage Messages、監査照合はView Audit Logを確認する。
- Timeout/Kick/Banは対応権限とRole階層を実行時にも検査する。

## 検証

```text
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build build-web
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build test-a11y
```

生成dist、依存ツリー、Playwright成果物は追跡ファイルに追加しない。APIと状態遷移の変更は[Web作業指示](tasks/WEB.md)に従う。
