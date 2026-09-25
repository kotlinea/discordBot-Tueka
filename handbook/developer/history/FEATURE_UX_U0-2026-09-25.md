# U0 情報設計・baseline（完了）

対象: `e1b47e9` の作業ツリー。2026-09-25、Windows / Docker Desktop Linuxコンテナ。開始時の計画関連5文書の未コミット変更を保持。

## 確定する表示構造

カテゴリーは見出し、機能は入口、操作は機能内に統一する。順序は「概要／サーバー情報」→サーバー運営→コミュニティ→エンゲージメント→モデレーション→通知・ソーシャル。Ticket/RRをサーバー運営の大機能とする。カテゴリーを開くための中間画面は必須にしない。既存のModeration/Social Hub URLはカテゴリー概要として保持する。

Guild共通の編集設定を持つ保存先は確認できなかったため、現在の「サーバー設定」は **サーバー情報** に改称し、Guild情報・Bot権限の読取画面へ変更する。個人の言語・外観・ナビ折畳みは個人設定に残す。Bot接続状況は新しいGuild別の実測契約を用意できる場合だけ表示し、Guild一覧にいることからオンラインと推測しない。

### 24機能の主配置とURL

URLは `/servers/:guildId/` からの相対表記。全URLを保持し、主入口だけ整理する。権限MはGuild管理者、Sは所属/担当を検証したTicket Staff。設定変更は全てM。表示カテゴリーを変えてもBackendカテゴリー・機能ID・DB所有者は変えない。

| 表示カテゴリー | 機能ID | 主入口 | 別設定入口 | 権限・画面 |
| --- | --- | --- | --- | --- |
| サーバー運営 | tickets | tickets | tickets/settings、modules/tickets | M/S。作業画面、Sは受付・履歴のみ |
| サーバー運営 | reaction_roles | reaction-roles | modules/reaction_roles | M。作業画面、一覧内設定Dialog |
| コミュニティ | welcome | modules/welcome | 同一 | M。入退室設定 |
| コミュニティ | autorole | modules/autorole | 同一 | M。参加ロール設定 |
| コミュニティ | leveling | modules/leveling | 同一 | M。XP・通知・報酬設定 |
| コミュニティ | live_stats | modules/live_stats | 同一 | M。統計Channel設定 |
| コミュニティ | temporary_voice | modules/temporary_voice | 同一 | M。一時VC設定 |
| エンゲージメント | advanced_polls | modules/advanced_polls | 同一 | M。機能有効化。投票の実行はDiscord |
| エンゲージメント | suggestions | suggestions | modules/suggestions | M。設定・提案審査を同画面で扱う |
| エンゲージメント | minigames | modules/minigames | 同一 | M。機能有効化。実行はDiscord |
| モデレーション | moderation | modules/moderation | 同一 | M。共通設定（表示名に用途を明記） |
| モデレーション | automod | moderation/automod | modules/automod | M。ルール一覧・編集 |
| モデレーション | anti_spam | moderation/anti_spam | modules/anti_spam | M。ルール一覧・編集 |
| モデレーション | anti_raid | moderation/anti_raid | modules/anti_raid | M。ルール一覧・編集 |
| モデレーション | infractions | moderation/infractions | modules/infractions | M。ユーザー履歴・閾値設定 |
| モデレーション | moderation_actions | moderation/moderation_actions | modules/moderation_actions | M。手動処置・機能設定 |
| モデレーション | moderation_logs | moderation/moderation_logs | modules/moderation_logs | M。履歴・ログ設定 |
| モデレーション | audit_log | moderation/audit_log | modules/audit_log | M。監査ログ設定 |
| モデレーション | trust_score | moderation/trust_score | modules/trust_score | M。Trust設定 |
| 通知・ソーシャル | youtube_updates | social/youtube | modules/youtube_updates | M。購読管理とModule設定 |
| 通知・ソーシャル | twitch_updates | social/twitch | modules/twitch_updates | M。同上 |
| 通知・ソーシャル | tiktok_updates | social/tiktok | modules/tiktok_updates | M。同上 |
| 通知・ソーシャル | x_updates | social/x | modules/x_updates | M。同上 |
| 通知・ソーシャル | instagram_updates | social/instagram | modules/instagram_updates | M。同上 |

### 機能内・共通の全画面入口

| 所属 | 現行URL／同一画面内の操作 | 整理後の場所 |
| --- | --- | --- |
| 共通 | `/servers`、Guild直下index、`settings`、個人設定Dialog、検索Dialog | Guild選択、概要、サーバー情報、Account、検索。URL維持 |
| カテゴリー | `moderation`、`social` | カテゴリー概要。主ナビの階層を変えない |
| Ticket | `tickets`、`inbox`、`inbox/:ticketId` | 機能概要→受付→詳細/返信/担当/Close等 |
| Ticket | `panels`、`panels/new`、`panels/:panelId` | 受付設定一覧→編集。既存6タブを保持 |
| Ticket | `panel-messages`、`forms`、`teams`、`tags` | 機能内の設定/定型文。新規作成は既存DialogまたはForm |
| Ticket | `transcripts`、`stats`、`settings` | 履歴、統計、共通設定。Sに許可する範囲は既存APIどおり |
| Ticket外部 | `/tickets/transcripts/:transcriptId`、添付・評価 | 本人/担当/管理者の既存認可。通常ナビに混ぜない |
| RR | `reaction-roles`、`new`、`:configId` | 一覧→作成/編集。設定Dialog・Link Groups・イベント・修復は機能内 |
| 3ルールFamily | `moderation/:family`、`rules/new`、`rules/:ruleId` | 一覧→編集。複製は新規ドラフト、テンプレートは作成時の選択 |
| Moderation補助 | 処置、履歴、ログ、監査/Trust設定（上表） | 個別機能。Preview/処置詳細は既存Dialog/編集手順内 |
| Social | `social/:provider` の一覧→Editor Dialog、Retry/削除 | Provider内操作。OAuth接続/callbackは既存Backend入口を保持 |
| Suggestions | `suggestions` 内の設定・一覧・審査 | 同じ機能内の領域として整理。新たな詳細Routeを仮定しない |
| 404・認証 | 未登録URL、Session失効→login、logout | 共通アプリ境界。架空の設定や別機能へ誘導しない |

Ticketの相対子URLは `tickets/`、RRの子URLは `reaction-roles/`、ルールの子URLは各Familyの主入口に続く。既存Routeの正本: `src/App.tsx`、`app/Shell.tsx`、`features/*/*.feature.tsx`、Ticket/RRの `Routes.tsx`、Moderation `RuleRoutes.tsx`。Bot専用Help等はこの画面一覧の対象外。

## 表示項目と保存・取得の棚卸し

### 共通と専用画面

| 項目 | 読取／更新の入口（`/api/v1`）と所有者 | 編集・更新タイミング／整理後の状態 |
| --- | --- | --- |
| Guild ID・名前・Icon、利用権限 | `/guilds`。Session認可とDiscord API | 読取のみ。Query再取得時。取得失敗/所属喪失を不明とする |
| Channel・Role・Emoji・Bot権限 | `/guilds/:id/resources`。Discord API | 候補は読取のみ、選択IDは各機能へ保存。開画面/Query再取得。削除済みIDは要修正 |
| 言語・appearance・color_scheme・navigation_collapsed | Session/preferences、`dashboard/repository.py` | 個人設定の明示保存とrevision。Guild設定へ移さない |
| enabled・設定値・revision・missing_permissions | `/guilds/:id/modules/:feature`、FeaturePresenter/SettingsAccess | 明示保存後再取得。enabledは設定値であり実稼働証明ではない |
| Ticket enabled/open_limit/retention/log/transcript Channel | `/guilds/:id/tickets/settings`、`ticketing` Repository | 管理者が専用保存。Module入口も同じ専用設定。取得失敗時はLoadingに留めずエラーへ |
| Ticket Panelの受付方式/名前/Team/Form/権限/時間/各Embed | `/tickets/panels` と個別ID、`ticketing` | 6タブで一つのドラフト→明示保存。公開操作と保存を区別 |
| Ticket Form質問、Team Role/User、PanelMessage送信先/Panel/Embed、Tag名前/内容 | `/tickets/forms`、`teams`、`panel-messages`、`tags` | 管理者。既存作成/更新契約を維持し、公開中/失敗は配送結果に基づく |
| Ticket受付/詳細/返信/Note/担当/履歴/統計 | `/tickets`、items等の専用API、`ticketing` | M/Sの既存権限。集計は読取、操作は明示実行。Hub等は5秒再取得 |
| RR enabled/log/denial DM/cooldown | `/reaction-roles/settings`、`reaction_roles` | SettingsDialogの明示保存、revision付き |
| RR投稿/Embed/振舞い/Role mapping/制約/期限、Link Group | `/reaction-roles/messages`、`link-groups` | 専用保存。active/pending/failed/locked/recoveryは実応答を表示。修復は独立操作 |
| ルールname/event_type/trigger/config/conditions/exemptions/actions/mode/enabled/priority/stop_on_match | `/moderation/:family/rules`、`moderation/repository.py` | 4段階編集と明示保存。順序変更は一覧。revisionとrules_revisionを保持 |
| Moderation Case/イベント/Lockdown/ポイント | overview、moderation専用API、`moderation` | 読取結果と処置要求を区別。共通/Family/ルールのON/OFFは別々 |
| Social account/Channel/events/templates/enabled、接続/配送エラー | `/social/:provider/subscriptions`、`social` | Editor明示保存、一覧5秒再取得。availability/Target状態/購読ONを別々に扱う |
| Suggestions設定・提案・投票/審査履歴 | `/suggestions/settings`、items等、`guild_settings`と`suggestions` | 設定はGuild Moduleの専用入力、審査はDomain操作。保存と審査を分離 |

各専用モデルの追加項目・Validationは `dashboard/api/schemas/`、画面入力は各機能のEditor/Settings、Domain正本は各Repository/Modelを照合対象とする。表示のためだけの新しい汎用保存テーブルを設けない。

### 汎用設定の項目（現在のMetadataに一致）

下表は全て `guild_settings/<category>/<feature>.py` の既定値/正規化と `guild_settings/repository.py` のModule保存を利用する。管理者がrevision付きで保存し、開画面・保存成功後・Query再取得時に更新する。未取得は無効とみなさない。

| 機能 | 項目 |
| --- | --- |
| welcome | welcome_enabled/channel_id/format/content、leave_enabled/channel_id/format/content |
| autorole | default_role_id |
| leveling | text_notification_channel_id、text_role_rewards、voice_enabled/notification_channel_id/role_rewards/xp_per_minute/allow_solo/allow_muted |
| live_stats | stats_channel_id、stats_template |
| temporary_voice | temp_voice_trigger_id、temp_voice_category_id、temp_voice_name |
| moderation | default_log_channel_id、immune_role_ids/user_ids/channel_ids、evidence_excluded_channel_ids/retention_days、exclude_bots/webhooks |
| automod / anti_spam | log_channel_id、immune_role_ids/user_ids/channel_ids（ルール本体とは別） |
| anti_raid | log_channel_id、notify_channel_id、default_lockdown_minutes、immune_role_ids/user_ids/channel_ids |
| infractions | point_thresholds、log_channel_id |
| moderation_logs | log_channel_id |
| audit_log | management_channel_id、log_message/voice/channel/member/role/server |
| trust_score | trust_retention_days、trust_flag_threshold |
| suggestions | channel_id、log_channel_id、review_role_ids、allow_voting、show_author、form_title、form_fields |
| advanced_polls / minigames / moderation_actions / Socialの5 Module | enabledのみ。Discord操作やSocial購読設定と混同しない |

### 実行可能性の表示契約

全機能の共通状態を「設定OFF／設定ON／要設定／権限不足／取得失敗」に分け、複数理由を保持する。ONだけで「稼働中」と断言しない。Moderationはcore→Family→ルールの実行条件（`cogs/moderation/runtime.py`）を根拠に親停止・有効ルール0件を追加表示。Ticketは受付enabledとTranscript可用性/配送状態、RRは設定enabledと投稿状態・復旧、SocialはModule/購読/Provider可用性/配送状態をそれぞれ表示する。未取得や通信失敗を0件・無効で埋めない。

## 操作差分と移行先

| 現行差分 | 後続段階で揃える契約 |
| --- | --- |
| 管理者がTicketを直リンクで開くと、overview取得を省くためcommunity/engagementのナビが空になる | NavigationのMetadata取得と画面固有overview取得を分離し、遷移先によって機能一覧を消さない。Staffには管理者用取得を要求しない（U1/U2） |
| 汎用設定はSaveBar、Ticket設定は常時保存Button、SocialはDialog | 未保存/保存中/成功/失敗/破棄を統一し、保存先は各Domainに保持（U3） |
| Ticket設定のQuery更新がdraftを再設定、取得失敗時Loadingが残る可能性 | 編集中の上書き防止と取得エラー表示（U3） |
| RR設定はDialog、Module設定URLも専用一覧 | 主入口と共通設定操作をRegistryへ宣言（U1〜U3） |
| Rule一覧は削除を逐次送信後に順序を保存 | 部分成功を隠さず結果を表示。新しい一括ON/OFFは単一Transaction（U3/U4） |
| Rule新規はenabled/enforce、複製操作なし | 複製は無効ドラフト、新ID、元不変。既定値選択と有効化を分離（U4/U5） |
| サーバー設定の説明/状態、Rule空状態のプリセット案内が実態と不一致 | 読取画面へ改称、実装済み操作だけ案内、日英更新（U2/U3/U5） |

## 簡潔な画面案と操作経路

<!-- Hallmark · pre-emit critique: P4 H4 E3 S5 R5 V3. Structure-only wireframes; existing visual tokens retained. -->

```text
共通ナビ                       Ticket作業画面
  概要 / サーバー情報            サポートチケット   [受付へ]
サーバー運営                   概要  受付  受付設定  履歴  統計  設定
  サポートチケット             選択した領域の一覧 → 詳細 → 元の一覧
  リアクションロール           Staff: 受付・履歴のみ
コミュニティ
  入退室 / 参加ロール …         RR作業画面
エンゲージメント                リアクションロール   [作成] [設定]
  投票 / 提案 / ミニゲーム       投稿一覧・状態・要対応 → 編集 → 一覧
モデレーション                 Link Group / イベントは機能内の領域
  共通設定 / AutoMod …
通知・ソーシャル                AutoMod
  YouTube / Twitch …           共通設定: ON  AutoMod: OFF  有効ルール: 0
                              [作成: 空/既定値] [選択を有効化] [無効化]
                              選択 | 名前 | 対象 | モード | 状態 | 編集/複製
                              編集→確認→保存→一覧（同じID）
```

Desktopはカテゴリー見出し+機能リンク、大機能内は局所Navigation。Mobileは同じ順序のDrawerで、操作後に閉じてFocusを画面見出しへ移す。320pxで操作Buttonを折り返し配置し、一覧は同じ項目順の縦配置にする。これは構造案であり、HTML画面の完成や表示検証を意味しない。

管理者の経路は「サーバー運営→Ticket→受付→詳細→受付」「Ticket→設定→保存→Ticket」「RR→設定Dialog→保存→一覧」「Moderation→AutoMod→編集→保存→一覧→機能設定→一覧」「Social→YouTube→編集Dialog→保存→一覧」。既存URLを保持して登録から戻り先も決定する。Staffは「Guild→Ticket→受付→詳細→受付」、設定への導線を出さずAPIも拒否する。実装後の初見ユーザビリティ受入はU2/U5でこの経路と照合する。

## baselineと実画面確認

現行ReactをPlaywrightで実描画し、HTTPは専用fixtureに置換した。実Discord/実Guildデータとの接続確認ではない。画像の機能名をIDとしている箇所はfixture由来であり、翻訳欠落の証拠にはしない。

Desktop画像で、サーバー設定とナビの機能重複、Ticket直リンク時の空カテゴリー、ルールの存在しないプリセット案内、StaffのTicket/受付/履歴への限定を確認した。320pxのDrawerでは上位リンクが横に連結・折返しされ、機能グループと表示方式が異なる。U2では縦の操作対象に揃える。375/768pxのRRでは設定・一覧・Link Group・履歴が一画面に並ぶため、機能内の領域Navigationで探しやすくする。これを配置・操作差分へ反映した。後続実装ではこの状態を維持することを目的にせず、上の構造案へ改善する。

実行入口: `docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build <task>`。以下は全てexit 0。ログは `artifacts/` 配下で閲覧確認済み。

| タスク | 結果・ログ |
| --- | --- |
| check | `check/20260925T082221-1e70d86b` |
| test-python | 418件。`test-python/20260925T082620-5d61ea0c` |
| api-check / commands-check | 生成物一致・103コマンド一致。`api-check/20260925T082539-f5159478`、`commands-check/20260925T082551-247003d4` |
| typecheck / test-web | 型検査・119件成功。`typecheck/20260925T082617-b57657ba`、`test-web/20260925T082637-55cc7804` |
| test-a11y | 既存88件＋画面記録4件成功。`test-a11y/20260925T082658-f625895c` |
| test-a11y ux-inventory.spec.ts | 管理者の受付/設定往復、Staffの設定非表示/受付往復、画面記録4件成功。RR Link Groupのmock不足を補完。`test-a11y/20260925T083220-2d6c1482` |
| 同 --project=desktop | 414px撮影前のスクロール位置を補正し1件成功。`test-a11y/20260925T083403-c957ecc1` |

初回Pythonは418件中1件が古い `FileExistsError` を期待して失敗（`test-python/20260925T082246-714d7f25`）。現行 `deploy/locking.py` の説明付き `ValueError` に合わせ、拒否後も元ロックが保持されるassertを追加した。Runtime実装は変更していない。再実行で全件成功。

画像は各ブラウザーログ下 `dashboard/frontend/test-results/ux-inventory-*/` の `server-settings`、`tickets`、`reaction-roles`、`rules`、`manager-navigation`、`staff-tickets`（png）。320/375/768pxとDesktop、追加414pxを記録し、上記の代表画像を目視した。空状態のfixtureによる構造確認であり、全実データの見た目が完成したという受入ではない。日英・既存保存/認可・直リンクは既存88ケースの範囲で受入。

U0の成果物は24機能/全入口対応、取得・保存・編集・更新タイミングの棚卸し、状態の定義、操作差分、ナビ/Ticket/RR/ルールの構造案、管理者/Staffの経路確認、現行baseline。全項目を満たしU0残作業なし。U1〜U6は計画どおりの後続実装であり、実環境への接続・配布は実施していない。

最終 `check-docs` はexit 0（`artifacts/check-docs/20260925T083532-7ccc51c0`）、`git diff --check` は指摘なし。検証用toolsを `down --remove-orphans` で終了した。
