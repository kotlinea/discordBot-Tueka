# G0 全入口対応表と変更前baseline

記録日: 2026-09-21。G0完了。対象Commitは `2b7050cb26acc85ea6edba080d5bf2af55458a18`。開始時は `goal.md` と制定履歴の2ファイルが追加済み・stage済みであり、その変更を保持した。本段階では実装・公開契約・DBを変更していない。

## 調査範囲と再現資料

AGENTS→HANDOFF、ENGINEERING、CODE_MAP、architecture、BACKEND/WEB、api/design/extending、DOCUMENTATION/TESTING/TOOLS、ROADMAP/EXECUTION_PLANを確認した。

- [機械抽出した固定一覧](FEATURE_STRUCTURE_G0-2026-09-21.json): 24機能、16拡張、8 Queue、103コマンド、59 APIパス/77操作、認可Fixtureの199ケース、Python 221ファイル、Frontend 87ファイル、計364ファイルの正規化SHA-256。
- [採取スクリプト](capture_g0_inventory.py): ASTのImport・decorator・引数・認可呼出し・テスト名、React Route宣言、生成OpenAPI、commands.jsonを抽出する。アプリをImportせず秘密値も読まない。静的一覧であり、実登録の一致は下記実行検証が保証する。
- 個別操作の完全なSchemaは対象Commitの `dashboard/api/openapi.json`、生成型は `dashboard/frontend/src/generated/api.ts`。固定一覧に操作別と全ファイルのハッシュを保持し、後段で差分を隠すためにbaselineを更新しない。
- 認可Fixtureのbodyは過去形式である。`tests/test_api_contract.py` は `error_detail` と `next: null` の変換後に現行応答と比較する。固定一覧もこの区別を保持している。

採取コマンド（リポジトリルート、出力は `artifacts/g0-inventory.json`）:

```text
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --no-deps --entrypoint python check-docs handbook/developer/history/capture_g0_inventory.py
```

固定一覧の `python` はファイル別の入口・静的依存、`frontend` は画面別の経路・API呼出し・Import、`commands` は別名を含む全コマンド、`api_operations` は全77操作、`features` は全設定Field/権限/親/日英Docs、`source_sha256` は比較元を示す。以下の表はその所有先と移設判断を示す。

## 機能ごとの所有先

略記: `C`=`cogs/`、`A`=`dashboard/api/`、`F`=`dashboard/frontend/src/features/`。`M`は現行の `A/modules.py` と `F/modules/Settings.tsx` による汎用設定。設定保存の `G` は `guild_settings/repository.py` の `guild_modules`、正規化は `guild_settings/models.py`。Docs列は `docs/` と `docs/en/` 共通の相対パス。テスト名は `tests/test_*.py` の中間部分を示す。

全24機能に、`features/<category>/<id>.py` と `F/<category>/<id>.tsx` の入口を設ける。既存の共有処理は表中の所有Domainが一度だけ起動する。機能の入口が別でも同じJobを各入口から起動しない。

| カテゴリー / ID | 現在のBot入力・処理 | API・画面 | 設定・所有Domain | Docs | 主な既存テスト |
| --- | --- | --- | --- | --- | --- |
| community / welcome | `C/welcome.py`: join/remove、`/welcome` | M | G / Welcomeメッセージ | features/welcome.md | welcome、storage、dashboard_v2 |
| community / autorole | 同じjoin内の初期Role付与 | M | G / Autorole | features/autorole.md | storage（設定保存） |
| community / leveling | `C/leveling.py`: message、4個のrank系コマンド、音声XP | M | G＋`community/`のXP/報酬 | features/leveling.md | leveling、community_repository、storage |
| community / live_stats | `C/community.py`: join/remove/update、5分更新 | M | G / Live Stats表示 | features/live-stats.md | storage（Template） |
| community / temporary_voice | `C/community.py`: voice state | M | G＋`community/`の一時VC記録 | features/temporary-voice.md | community_repository、storage |
| community / reaction_roles | `C/reaction_roles.py`: raw reaction/message delete、`reactionrole`/`r` | `A/reaction_roles.py`、`F/reaction-roles/` | `reaction_roles/`専用設定/Repository/Service | features/reaction-roles.md | reaction_roles、reaction_role_changes、delivery_native_errors |
| community / tickets | `C/tickets.py`: interaction/message/edit/delete/member remove、`ticket`/`t` | `A/tickets.py`＋`ticket_configuration.py`、`F/tickets/` | `ticketing/`、TranscriptStorage、専用設定 | features/tickets.md | ticketing_v2、ticket_panel_delivery、ticket_discord_adapter、ticket_recovery_api、ticket_migration、transcript_storage |
| engagement / advanced_polls | `C/engagement.py`: `/poll`、interaction、期限処理 | M | G＋`engagement/`のPoll/投票 | features/polls.md | storage、domain_boundaries |
| engagement / suggestions | `C/suggestions.py`: `/suggest`、Modal/interaction | `A/suggestions.py`、`F/suggestions/Settings.tsx` | G＋`suggestions/`、専用APIで正規化 | features/suggestions.md | suggestions、suggestions_api、suggestions_cog、suggestion_delivery |
| engagement / minigames | `C/engagement.py`: `/rps` | M | G / 勝敗処理、永続戦績なし | features/minigames.md | features/startupの登録。専用勝敗テストなし |
| moderation / moderation | `C/moderation.py`の`/clear`、共通処置の有効化 | M＋`F/moderation/Hub.tsx` | G＋`moderation/` | features/moderation.md | automod_storage、moderation_commands、safety |
| moderation / automod | `C/automod.py`: 共通イベント評価 | `A/moderation.py`のfamily、`F/moderation/RuleList/RuleEditor` | G＋同DomainのRule/Engine/Service | features/automod.md | automod、automod_storage、moderation_adapter |
| moderation / anti_spam | 同共通評価（message/reaction） | 同family=`anti_spam` | G＋同Domain | features/anti-spam.md | automod、automod_storage |
| moderation / anti_raid | 同共通評価（join/remove等）・Raid状態 | 同family=`anti_raid` | G＋同DomainのRaid/Lockdown | features/anti-raid.md | automod、moderation_adapter、resource_leases |
| moderation / infractions | Safety/ModのwarnがCase/Pointを更新 | `A/moderation.py`のinfractions、`F/moderation/Infractions.tsx` | G＋同DomainのCase/Point | features/infractions.md | safety、moderation_commands、automod_storage |
| moderation / moderation_actions | `C/safety.py`の4コマンド＋`moderation_commands.py`の12個 | actions API、`F/moderation/Actions.tsx` | G＋同Domainの処置/Lease | features/moderation-actions.md | safety、moderation_commands、moderation_adapter、resource_leases |
| moderation / moderation_logs | 共通処置/評価が監査Eventを生成 | events API、`F/moderation/Logs.tsx` | G＋同DomainのEvent/証拠 | features/moderation-logs.md | automod_storage、api_contract |
| moderation / audit_log | `C/audit_log.py`の20イベント＋`C/moderation.py`の`/set_management` | M。専用Routeはない | G＋同Domainへの監査保存 | features/audit-log.md | audit_log、domain_boundaries、storage |
| moderation / trust_score | `C/trust.py`の照会/解除、24時間purge | M。専用Routeはない | G＋同DomainのTrust Event | features/trust-score.md | storage、automod_storage |
| social / youtube_updates | `C/social_updates.py`配送、Worker取得、YouTube webhook | `A/social.py`、`F/social/Provider.tsx` | G＋`social/`の購読/Target/Event | social/youtube.md | social_updates、social_worker、social_adapter |
| social / twitch_updates | 同配送/取得、Twitch webhook | 同provider=`twitch` | G＋同Domain | social/twitch.md | social_updates、social_worker、social_adapter |
| social / tiktok_updates | 同配送/取得、Provider OAuth | 同provider=`tiktok` | G＋同DomainのToken/OAuth state | social/tiktok.md | social_updates、social_worker、storage |
| social / x_updates | 同配送、Workerのstream/poll | 同provider=`x` | G＋同Domain | social/x.md | social_updates、social_worker |
| social / instagram_updates | 同配送/取得、Provider OAuth | 同provider=`instagram` | G＋同DomainのToken/OAuth state | social/instagram.md | social_updates、social_worker、storage |

全機能共通の検証は `features`、`guild_settings`、`api_contract`、`api_schema`、`api_architecture`、`dashboard_v2`、`v2_startup`。表の関連テストは該当Domainを検証するものであり、全実Discord動作を保証するという意味ではない。

## 16拡張の移設と登録外機能の扱い

| 現在の拡張 | 移設先・分解単位 | 起動所有者と判断 |
| --- | --- | --- |
| `cogs.general` | `cogs/core/{help,ping,userinfo,serverinfo}.py`、`cogs/engagement/{echo,calculate,roll}.py` | Help/Ping/ユーザー・Guild情報はアプリ基盤の明示登録。Echo/計算/Diceは既存のBot専用機能としてengagementのRegistryへ登録 |
| `cogs.ai` | `cogs/engagement/gemini.py` | 既存GeminiコマンドをBot専用として登録。APIキーなしの応答を維持 |
| `cogs.leveling` | `cogs/community/leveling.py` | Levelingが音声XP Taskを一つ所有 |
| `cogs.moderation` | `cogs/moderation/moderation.py`と`audit_log.py` | `/clear`と`/set_management`を所有機能へ分け、コマンド名/権限/有効化条件を維持 |
| `cogs.safety` | `cogs/moderation/moderation_actions.py`の専用補助へ | `/warn /timeout /kick /ban`を同じ処置機能の入口として維持 |
| `cogs.reaction_roles` | `cogs/community/reaction_roles.py`＋`reaction_role_support/` | Reaction Rolesが全別名・Modal・3 Taskを所有 |
| `cogs.automod` | `cogs/moderation/runtime.py`＋各機能の入力処理 | Moderationカテゴリーの共通Dispatcherが複数familyの評価順・stop・dedupe・2 Queue・Lockdown復旧を一度だけ実行 |
| `cogs.moderation_commands` | `cogs/moderation/moderation_actions.py`の専用補助へ | `/mod` Groupは一度だけ登録。上記Safetyとの入口統合で旧コマンドも維持 |
| `cogs.community` | `cogs/community/{live_stats,temporary_voice}.py` | 統計イベント/TaskとVCイベントを分ける。Repositoryの所有はcommunityのまま |
| `cogs.tickets` | `cogs/community/tickets.py`＋`ticket_support/` | TicketがView/Modal/4 Task/起動時復旧を所有 |
| `cogs.engagement` | `cogs/engagement/{advanced_polls,minigames}.py` | Pollだけがinteraction/期限Taskを所有 |
| `cogs.suggestions` | `cogs/engagement/suggestions.py` | SuggestionsがModal/interaction/Outbox Taskを所有 |
| `cogs.trust` | `cogs/moderation/trust_score.py` | Trustが照会/解除/purgeを所有 |
| `cogs.audit_log` | `cogs/moderation/audit_log.py` | Audit Logが20イベントを所有、`set_management`もここへ合流 |
| `cogs.welcome` | `cogs/community/{welcome,autorole}.py` | 現在のjoin内の2機能を分離。Welcome無効でもAutorole有効ならRole付与する条件を保持 |
| `cogs.social_updates` | `cogs/social/delivery.py`＋各Provider機能Binding | Socialカテゴリーが共通配送Taskを一つ所有。Provider登録の数だけ起動しない |

Bot専用のecho/calculate/roll/geminiは既存動作の整理であり、新しい公開Dashboard機能ではない。Backend定義はDashboard Metadataを省略可能にし、公開24機能とそのIDを保持する。新しいGuild有効化フラグも足さない。Docsは `docs/reference/commands.json` と日英生成コマンドページ、検証は `general`・`commands-check`・`v2_startup`（Geminiの外部API成功は未検証）。

Pythonでは `tickets.py` と同名の `tickets/__init__.py` を併設しない。補助パッケージは `ticket_support/` 等の異なる名前を使用する。Frontendの既存 `tickets/` は維持可能だが、機能入口と内部画面のImport先は明示する。

## Event・Task・Workerの所有境界

全Eventの正確な名前/decorator/行は固定一覧の `python["cogs/…"].entries` に保持した。全listenerは上記16拡張表の一つに属する。UI Button/Modalのcallbackも同じCogの所有とし、永続custom_idの文字列を維持する。

| 現在の実行入口 | 周期・入力 | 所有先・移行時の不変条件 |
| --- | --- | --- |
| Leveling `voice_xp_tick` | 60秒 | Leveling。message XPと保存trackを混ぜない |
| Community `refresh_live_stats` | 5分＋member join/remove/update | Live Stats。VC作成/削除は別listener |
| Engagement `close_expired_polls` | 30秒 | Advanced Polls。投票custom_idと期限後の投票拒否 |
| AutoMod `maintenance` | 60秒 | Moderation共通Runtime。証拠purge/Engine prune、期限処置、Lockdown復元、stale Raid解除、Dashboard要求を現行順序で実行 |
| Reaction Roles `process_outbox/process_schedules/maintenance` | 5秒/15秒/1時間 | Reaction Roles。before_outboxの保留Role変更復旧、Lease/補償/修復を保持 |
| Tickets `deliver_outbox/auto_close/publish_panels/maintain_transcripts` | 5秒/1分/10秒/1時間 | Ticket。before_auto_closeの作成/Claim復旧と未完了Close復旧、暗号化/保持期間を保持 |
| Suggestions `deliver_outbox` | 5秒＋操作直後のrun_batch | Suggestions。予約と状態保存の同一Transaction、配送結果不明時の照合 |
| Trust `purge_expired_data` | 24時間 | Trust。設定の保持期間と無効Guildの条件 |
| Social `deliver_events` | 5秒 | SocialカテゴリーのBot配送。Provider別の有効化判定と部分失敗再試行 |
| `social/worker.py`の`poll_loop/x_stream_loop/heartbeat_loop` | runからgather、DBの次回取得時刻/stream/10秒heartbeat | 別Process `social-worker`。Providerの監視Lease、CursorとEventの同時保存、Token更新、終了処理を維持 |
| `bot.py`・`dashboard/app.py`のlifespan、`observability/heartbeat.py` | 起動/終了・heartbeat | アプリ基盤。Feature Registry読込では起動せず、Process初期化からのみ実行 |

8 Queueの一意な実行所有者:

| Queue | Repository | 実行入口 |
| --- | --- | --- |
| `ticket_outbox` | `ticketing/repository.py` | Ticket `deliver_outbox` |
| `ticket_schedules` | 同上 | Ticket `auto_close` |
| `reaction_role_outbox` | `reaction_roles/repository.py` | Reaction Roles `process_outbox` |
| `reaction_role_schedules` | 同上 | Reaction Roles `process_schedules` |
| `moderation_action_requests` | `moderation/repository.py` | Moderation `maintenance` |
| `scheduled_moderation_actions` | 同上 | 同上 |
| `social_events` | `social/repository.py` | Social Bot `deliver_events`（取得Workerではない） |
| `suggestion_outbox` | `suggestions/repository.py` | Suggestions `deliver_outbox`/即時batch |

Panel公開・Resource Lease・継続Provider監視を新Queueへ変換しない。`jobs/catalog.py` のSQL列対応、retry/lease/token/retentionと各Domainの補償を保持する。

## 全APIと認可の移設

77操作は固定一覧の `api_operations` にmethod/path/operationId/parameters/statuses/契約ハッシュを保持する。下表の条件は排他的で、すべての操作を覆う。URL変更・追加の別名URLは行わない。

| 現在のRouter・操作数 | 移設先・所有者 | 認可・保存境界 |
| --- | --- | --- |
| `A/session.py`＋`guilds.py`: 6 | アプリ基盤に保持 | Session/個人設定/利用可能Guild、Guild概要/機能/Resource。Guild選択はTicket Staffも考慮 |
| `A/modules.py`: 2 | 共通Module Routerを保持、個別設定契約をRegistryから解決 | GETは管理者、PUTはCSRF＋live管理者＋Resource/必要権限。Ticket/Reaction Rolesの汎用PUT拒否を維持 |
| `A/moderation.py`: 11 | `A/moderation/`のRule共通Router、infractions、moderation_actions、moderation_logs | family別機能はRule共通Routerを一度登録。未知family検査と認可の優先順、Rule/revisionの同時更新 |
| `A/reaction_roles.py`: 14 | `A/community/reaction_roles.py`＋専用補助 | 管理者＋更新CSRF、削除If-Match、別Guild/Role階層・修復 |
| `A/social.py`: 7 | `A/social/`共通Routerを一度登録、Provider Bindingで分岐 | 管理者＋更新CSRF、Provider/購読revision、同じTargetの所有契約 |
| `A/suggestions.py`: 3 | `A/engagement/suggestions.py` | 管理者＋更新/previewのCSRF、設定とDomain正規化 |
| `A/tickets.py`＋`ticket_configuration.py`: 34 | `A/community/tickets.py`＋`ticket_support/` | 設定は管理者、Inbox/操作はStaff/担当Team、Transcript/添付は申請者も可。退Guild後のTeam user IDで許可しない |

補助ファイルの扱い:

- `context.py` は共通ContextとDomain Factoryの合成へ変更。各アプリのRepository/Serviceを注入し、ModuleのImport時に作らない。
- `ticket_dependencies.py/ticket_resources.py/ticket_presentation.py` は `community/ticket_support/` へ。`ticket_configuration.py` のforms/teams等の動的生成Routeも34操作に含む。
- `dependencies.py/resources.py/errors.py/serialization.py/route.py/body.py` はAPI共通基盤に保持。`features.py` のTicket/Reaction Roles別分岐は機能ごとの設定読取Bindingへ。
- `schemas/` と生成ファイルは契約正本として保持する。専用Schemaの所在地変更が必要な場合だけ機能単位で移設し、operationIdやJSONを変えない。

`dashboard/app.py`にはAPI外の入口もある。`/`、`/login`、`/oauth/callback`、`/logout`、SPA配信(`/servers`以下・`/tickets/transcripts/{id}`)、`/tokens.css`、`/favicon.ico`、`/static`、`/ui`、`/docs`、例外/middlewareはアプリ基盤。`/social/oauth/{provider}/connect/{guild_id}`・callbackとYouTube GET/POST・Twitch POST webhookはSocial所有のHTTP Bindingへ移設する。OAuth開始のSession/フォームCSRF/live管理者、callback state、webhook署名/検証を保持する。

`observability/http.py`の `/health/live`、`/health/ready`、`/internal/metrics` は監視基盤。Swagger/OpenAPIのDev限定条件、Docs/管理画面未build時の応答、監視Tokenを機能登録へ巻き込まない。

## 全画面・Route・共有要素

`F`配下の画面、`App.tsx`、`app/`、`routing/`、共有部品、翻訳、生成型の全87ファイルを固定一覧で列挙した。下表はRoute宣言を親経路と合成したもので、`g`は`:guildId`。

| 現行経路 | 現行の画面所有 | 移設先 |
| --- | --- | --- |
| `/servers` | `F/guilds/ServerPicker` | アプリ基盤 |
| `/servers/g`、`/servers/g/settings` | `F/guilds/Overview,Settings`＋Shell | アプリ基盤。RegistryからNavigationを構成 |
| `/servers/g/modules/:moduleId` | `F/modules/Settings` | 共通設定画面。機能Field/表示/検証を各機能ファイルへ |
| `/servers/g/moderation` | `F/moderation/Hub` | moderationカテゴリーHub |
| 同 `/automod /anti_spam /anti_raid`、`/:family/rules/new`、`/:family/rules/:ruleId` | RuleList/RuleEditor/ActionConfigDialog/ruleForm | 各機能入口＋moderation内共有Rule編集 |
| 同 `/infractions /moderation_actions /moderation_logs` | Infractions/Actions/Logs、Events表示 | 対応する機能入口 |
| `/servers/g/tickets`＋`/inbox`、`/inbox/:ticketId` | Ticket Hub/Inbox/Detail | `F/community/tickets/` |
| 同 `/panels`、`/panels/new`、`/panels/:panelId`、`/panel-messages`、`/forms`、`/teams` | Panels/PanelEditor/Configuration | 同上 |
| 同 `/settings /transcripts /tags /stats` | Settings/Archive/Configuration/Stats | 同上 |
| `/tickets/transcripts/:transcriptId` | Ticket TranscriptStandalone | Ticket所有。Guild Shell外のRouteとして登録 |
| `/servers/g/reaction-roles`＋`/new /:configId` | Overview/Editor、SettingsDialog/LinkGroups | `F/community/reaction_roles.tsx`＋内部画面。未知子Routeの相対redirectを維持 |
| `/servers/g/suggestions` | Suggestions Settings | `F/engagement/suggestions.tsx` |
| `/servers/g/social`＋`/:provider` | Social Hub/Provider/Editor | SocialカテゴリーHubとProvider入口 |
| Root `*`、Guild `*` | `/servers` redirect / NotFound | アプリ基盤。未知Routeを新しい機能に吸収しない |

Account、Preferences、CommandPalette、Breadcrumb、Session取得はアプリ基盤。Ticket StaffだけのGuildではTicketへredirectし、管理概要を取得しない条件を保持する。

共有部品は `components/EmbedEditor.tsx`→`components/editors/EmbedEditor.tsx`、新しい標準Button→`components/ui/Button.tsx`、既存のSaveBar/Feedback/ResourcePicker/PermissionDiagnostics/AccessPolicy/ScheduleEditor/EmojiPicker/formsは共有として保持・整理する。Ticket変数や保存APIは機能側が所有する。

翻訳Namespaceは現行のcommon/moderation/tickets/reactionRoles/social/suggestionsを維持する。読み込み方式変更は本移設の必須条件にせず、日英Key照合とlazy Routeの依存方向を維持する。

## 依存・同梱の変更点

1. 現在は `config.Settings.extensions`→`bot.setup_hook`、`api_v1.create_api_router`→各Router、`Shell`→画面loaderという3つの手動合成がある。移行後はそれぞれのRegistryを消費する薄い合成入口にする。
2. `feature_registry.py`→`dashboard.icon_registry`の逆向き依存を解消する。機能定義はIcon ID文字列を保持し、存在検査をDashboard側へ置く。
3. `GuildSettingsRepository`→機能別normalizer/`suggestions.normalize_settings`、API modules→機能別if、FeaturePresenter→専用Repositoryの依存をBinding注入へ変更する。RepositoryのSQL・lock・Transactionは保持する。Domainから上位RegistryをImportして循環させない。
4. `F/modules/Settings.tsx`→`F/moderation/ruleForm.ts`の`lines`、PermissionNotice→guilds画面等は共通化候補。単純な値変換/診断表示だけを共通側へ移し、Rule業務全体を共通部品へ持ち込まない。
5. TicketのOutboxと状態、Moderation Ruleとrevision/CaseとTrust、Social EventとCursorの同一Transactionを分離しない。DBテーブル名・Migration番号・暗号鍵・Volumeは変更しない。
6. `runtime/__main__.py`の5入口（bot/dashboard/social-worker/migrate/test）、`social_worker.py`、`migrate.py`、`database/`、`jobs/`、監視/復旧/運用CLIは基盤として保持する。
7. `Dockerfile`はPythonパッケージを明示COPYする。新しいルート`features/`はG1で使用開始するときにCOPYへ追加する。testsの旧Import、commands生成元のmodule名、API contract fixtureの内部operationId、Docs参照、toolsの作業コピーも同じ移行単位で確認する。103コマンドの公開名/引数は維持し、内部module移設だけの生成差分を区別する。

## 既存の限界と移行時の受入項目

G0の6タスクには失敗なし。以下は調査で確認した構造・検証範囲であり、G0の検証を未実施のまま残したものではない。

- AutoroleはWelcomeと同じjoin関数にある。現在のテストは保存設定とWelcome文字列が中心で、二つの有効/無効の組合せとRole付与の一回性はG2の分離で検証する。
- `featurePath`はparent=moderationなら `/moderation/{id}` を返すが、audit_log/trust_scoreの専用Route宣言はない。汎用 `/modules/{id}` は存在する。現状の経路不整合として固定し、G4で有効な汎用経路への登録を明示する。既存の有効URLを削除せず、これを移設による欠落と混同しない。
- 汎用ModuleSettingsは不明moduleId時にLoadingを返す。Live Stats/Minigamesの専用実動作テスト、全機能の実Discord受入は現在の成功から証明できない。変更対象の動作をG2〜G4で追加確認する。
- `test_features.py`はMetadata/Docs/Iconを確認するが、ID重複・親循環・起動Binding衝突の拒否を網羅しない。G1/G5で契約テストを追加する。
- `test-web`は3ファイル14テスト（API4、Design5、Suggestions5）。Playwrightの全画面検証ではない。e2e/dashboard.spec.tsにRule/Social/Ticket/共通Form/外観等の検査があり、G2/G4で実行する。
- 静的Import一覧は全Pythonファイルを含むが、実行時の依存だけを意味しない。テスト専用Importと将来AutoMod同期Portを現行の稼働機能と取り違えない。

## 変更前検証の証拠

環境: Windows Host / Docker Desktop、Linuxコンテナ、Python 3.13.15。実環境app.envを使用せず、専用PostgreSQLのUUID Schemaで検証。下記ログはローカルで存在と閲覧を確認済み。`artifacts/`はGit管理対象外なので、要点を本書に残す。

リポジトリルートで実行:

```text
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build check
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build test-python
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build typecheck
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build test-web
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build api-check
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build commands-check
```

| タスク | 結果 | `artifacts/`配下のログディレクトリ |
| --- | --- | --- |
| check | exit 0、Linux daemon/Compose/mount/書込可 | `check/20260921T053227-eeb23b62` |
| test-python | exit 0、374件成功、117.625秒 | `test-python/20260921T053250-541aca3a` |
| typecheck | exit 0、TypeScript成功 | `typecheck/20260921T053316-01ab8ed8` |
| test-web | exit 0、3ファイル14件成功 | `test-web/20260921T053409-23a0ff32` |
| api-check | exit 0、生成OpenAPI/TypeScript一致 | `api-check/20260921T053631-06797403` |
| commands-check | exit 0、103コマンドの登録/引数/日英一致 | `commands-check/20260921T053702-b3e99527` |

各ディレクトリの `result.json` と `task.log` を確認した。PythonにはStarlette/httpx・discordの非推奨警告、テスト用Discord Intent警告、asyncio遅延警告があるが、失敗/skipではない。検索時にPowerShellで未展開のglobをrgへ渡したエラーはディレクトリ指定へ修正し、棚卸しの欠落を残していない。

文書更新後の `check-docs` もexit 0（`artifacts/check-docs/20260921T054447-eaffbf5a`）。364ファイルのハッシュを現行ツリーと再照合し一致、24機能行・16拡張行・103コマンドの所有拡張を照合した。`git diff --check` と新規ファイルの行末空白検査も成功。LF→CRLFの通知は空白エラーではない。既存stageの2ファイルは保持した。

```text
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build check-docs
git diff --check
docker compose --env-file deploy/compose.env -f compose.tools.yaml ps --all --format json
docker compose --env-file deploy/compose.env -f compose.tools.yaml rm --stop --force postgres-test
```

片付け時に `down --remove-orphans` は自動承認レビューで拒否された（同じProjectの別サービスを停止する可能性）。一覧で今回作成した `postgres-test`（ID `32832e079994`）だけが残っていることを確認し、上記のサービス限定操作で停止・削除成功。実環境サービス・Volumeの操作はない。拒否に起因する未完了作業はない。

## G0完了判定

- [x] 24公開機能のCog/API/画面/設定/Domain/日英Docs/既存テストを対応付けた。
- [x] Registry外の全コマンドを基盤またはBot専用機能へ分類した。
- [x] 16拡張の全listener/Task/callback、別Worker、8 Queue、全HTTP入口、全Routeを所有先へ対応付けた。
- [x] 移設先と共有ライフサイクル、保持すべき認可/Transaction/依存/同梱条件を決めた。
- [x] 6つの指定baselineタスクを実行し、成功結果と既存の検証限界を分離した。

G0の残作業・阻害要因なし。次はG1の型・明示Registry・拒否検証。Linux Host/Remote CI/実Stageの受入は全体計画の別ゲートであり、今回のローカルbaselineで完了扱いにしない。
