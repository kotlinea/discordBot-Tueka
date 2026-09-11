# V1削除Inventory（2026-09-10）

対象はローカル設定先 `data/tueka.sqlite3` のBackup Snapshot。遠隔本番DBの存在・一致は未確認。行内容・Guild/User ID・Tokenは含めない。列、外部キー、Index、静的参照位置の全一覧は `schema-0910.json`。

## テーブル単位の判定

| テーブル | Snapshot行数 | 判断 | 直接SQL参照ファイル |
| --- | ---: | --- | --- |
| `app_metadata` | 0 | 保持 | `storage.py` |
| `automod_events` | 0 | P1-4で削除（参照除去後） | `storage.py` |
| `automod_migrations` | 1 | P1-4で削除（参照除去後） | `storage.py` |
| `automod_rules` | 0 | P1-4で削除（参照除去後） | `storage.py`, `dashboard/app.py` |
| `dashboard_preferences` | 1 | 保持 | `storage.py`, `dashboard/api_v1.py` |
| `dashboard_sessions` | 1 | 保持 | `storage.py` |
| `guild_modules` | 16 | 保持 | `storage.py`, `ticketing/repository.py`, `reaction_roles/repository.py` |
| `guild_settings` | 1 | 保持 | `storage.py`, `dashboard/api_v1.py` |
| `guild_users` | 2 | 保持 | `storage.py` |
| `guild_voice_users` | 2 | 保持 | `storage.py` |
| `moderation_action_requests` | 0 | 保持 | `storage.py` |
| `moderation_action_results` | 0 | 保持 | `storage.py` |
| `moderation_cases` | 1 | 保持 | `storage.py` |
| `moderation_events` | 16 | 保持 | `storage.py` |
| `moderation_lockdown_snapshots` | 0 | 保持 | `storage.py` |
| `moderation_lockdowns` | 0 | 保持 | `storage.py` |
| `moderation_migrations` | 1 | P1-4で削除（参照除去後） | `storage.py` |
| `moderation_points` | 0 | 保持 | `storage.py` |
| `moderation_raid_state` | 0 | 保持 | `storage.py` |
| `moderation_rules` | 2 | 保持 | `storage.py`, `cogs/automod.py`, `dashboard/api_v1.py`, `dashboard/app.py` |
| `oauth_states` | 0 | 保持 | `storage.py` |
| `poll_votes` | 0 | 保持 | `storage.py` |
| `polls` | 0 | 保持 | `feature_registry.py`, `storage.py`, `cogs/engagement.py` |
| `reaction_role_access_roles` | 0 | 保持 | `reaction_roles/repository.py` |
| `reaction_role_assignments` | 2 | 保持 | `reaction_roles/repository.py` |
| `reaction_role_binding_receipts` | 0 | 保持 | `reaction_roles/repository.py` |
| `reaction_role_events` | 20 | 保持 | `dashboard/api_v1.py`, `reaction_roles/repository.py` |
| `reaction_role_link_groups` | 0 | 保持 | `dashboard/api_v1.py`, `reaction_roles/repository.py` |
| `reaction_role_mappings_v2` | 2 | 保持 | `reaction_roles/repository.py` |
| `reaction_role_messages_v2` | 1 | 保持 | `reaction_roles/repository.py` |
| `reaction_role_outbox` | 10 | 保持 | `reaction_roles/repository.py` |
| `reaction_role_panels` | 0 | P1-3で削除（参照除去後） | `storage.py` |
| `reaction_role_recovery` | 1 | 保持 | `reaction_roles/repository.py` |
| `reaction_role_schedules` | 0 | 保持 | `reaction_roles/repository.py` |
| `reaction_role_settings` | 1 | 保持 | `reaction_roles/repository.py` |
| `safe_browsing_cache` | 0 | 保持 | `storage.py` |
| `scheduled_moderation_actions` | 0 | 保持 | `storage.py` |
| `social_connections` | 0 | 保持 | `storage.py`, `dashboard/app.py` |
| `social_deliveries` | 2 | 保持 | `storage.py` |
| `social_events` | 1 | 保持 | `storage.py` |
| `social_live_messages` | 0 | 保持 | `storage.py` |
| `social_oauth_states` | 0 | 保持 | `storage.py` |
| `social_subscriptions` | 1 | 保持 | `storage.py`, `dashboard/api_v1.py`, `dashboard/app.py` |
| `social_targets` | 1 | 保持 | `social_worker.py`, `storage.py` |
| `social_worker_state` | 13 | 保持 | `storage.py` |
| `support_tickets` | 0 | P1-2で削除（参照除去後） | `storage.py`, `ticketing/repository.py` |
| `temporary_voice_channels` | 1 | 保持 | `storage.py` |
| `ticket_attachments` | 0 | 保持 | `ticketing/repository.py` |
| `ticket_audit_events` | 0 | 保持 | `ticketing/repository.py` |
| `ticket_blacklist` | 0 | 保持 | `ticketing/repository.py`, `ticketing/service.py` |
| `ticket_close_requests` | 0 | 保持 | `ticketing/repository.py` |
| `ticket_counters` | 0 | 保持 | `ticketing/repository.py` |
| `ticket_feedback` | 0 | 保持 | `dashboard/api_v1.py`, `ticketing/repository.py` |
| `ticket_forms` | 0 | 保持 | `dashboard/api_v1.py`, `ticketing/repository.py` |
| `ticket_guild_settings` | 0 | 保持 | `ticketing/repository.py` |
| `ticket_messages` | 0 | 保持 | `ticketing/repository.py` |
| `ticket_migrations` | 1 | P1-2で削除（参照除去後） | `ticketing/repository.py` |
| `ticket_on_call` | 0 | 保持 | `cogs/tickets.py`, `ticketing/repository.py` |
| `ticket_orphans` | 0 | 保持 | `ticketing/repository.py` |
| `ticket_outbox` | 0 | 保持 | `ticketing/repository.py` |
| `ticket_panel_messages` | 0 | 保持 | `cogs/community.py`, `dashboard/api_v1.py`, `ticketing/repository.py` |
| `ticket_panels` | 0 | 保持 | `dashboard/api_v1.py`, `ticketing/repository.py` |
| `ticket_participants` | 0 | 保持 | `ticketing/repository.py` |
| `ticket_schedules` | 0 | 保持 | `ticketing/repository.py` |
| `ticket_staff_teams` | 0 | 保持 | `ticketing/repository.py` |
| `ticket_tags` | 0 | 保持 | `cogs/tickets.py`, `dashboard/api_v1.py`, `ticketing/repository.py` |
| `ticket_transcripts` | 0 | 保持 | `dashboard/api_v1.py`, `ticketing/repository.py` |
| `tickets_v2` | 0 | 保持 | `config.py`, `cogs/community.py`, `cogs/tickets.py`, `dashboard/api_v1.py`, `dashboard/app.py`, `ticketing/repository.py` |
| `trust_events` | 0 | 保持 | `storage.py` |

## 判断境界

- Snapshotの69テーブル・101行は別DB復元後も一致。integrity_check成功、foreign_key_check違反0件。
- SQL文字列の静的参照一覧は呼出しGraphそのものではない。Repositoryメソッドを呼ぶCog/APIも削除時に追跡する。
- Suggestionsの3テーブルはこのSnapshotにない。現在のソースが初期化する `suggestions` / `suggestion_votes` / `suggestion_events` はV2として保持・Migration新規作成対象。
- テーブルが空でも削除根拠にしない。V2のTicket、Role付与状態、Social配送、Moderation Case/Eventは保持する。
- `guild_modules`、`guild_settings`、`guild_users`、`moderation_cases`、`moderation_points`、`scheduled_moderation_actions` は共有/V2利用があるためテーブル全体を削除しない。

## 列・参照と削除順

- P1-1: Dashboard Flag/Allowlist、管理Jinja/旧POSTを除去。`/api/v1`、認証・公開Landing・DocsとSPA正式URLは保持。DB共有設定を削除しない。
- P1-2: 旧Ticket Cog/委譲と `migrate_legacy` / `legacy_plaintext_transcripts` 呼出しを除去してから `support_tickets` / `ticket_migrations` を削除。V2 Transcript・Outbox/Scheduleは保持。
- P1-3: Safety旧ボタン・旧Panel保存、API Legacy表示/Wizard・旧公開コマンドを除去してから `reaction_role_panels` を削除。V2設定・付与状態・期限・修復データは保持。
- P1-4: `moderation_points.rule_id` / `automod_event_id` の旧外部キーを外し、`moderation_rule_id` / `moderation_event_id` を保持する。`moderation_cases` の同名旧列・`moderation_rules.legacy_rule_id` も読書きを除去してから番号付きMigrationで削除する。
- `moderation_points` の旧FKを解消する前に `automod_events` / `automod_rules` をDROPしない。旧Events→旧Rules→移行判定表の順で除去し、foreign_key_checkを行う。
- `guild_users.warn` はXPと同居。警告Fallback利用を追跡して列のみ除去し、XPを保持する。`guild_settings` の管理/welcome/autorole既定値依存は別途現行設定へ整理するまで保持する。
- P1-5: `migrate_json.py`、`app_metadata` のJSON移行済み判定を除去。`app_metadata` 自体は汎用Metadata境界として保持する。
- 各削除Migrationは先に自動Snapshot、DDLとデータ更新をTransactionで実行し、失敗Rollback・空DB・既存V2・混在・再適用を検証する。Runtime initializeが削除表を再作成しないことも確認する。

## 復旧と未確認事項

- 2026-09-12追記：P1-4の0004で旧AutoMod/移行判定4表と旧ID/Warning列を除去。P1-3複製DBに適用し、保持65表98行の保持列一致・整合性・FKを確認。現行Rule/Event/処置結果のリンクは混在Fixtureでも検証した。原DBには未適用。上表の時点Inventoryは書き換えない。

- 2026-09-11追記：P1-3で `reaction_role_panels` のRuntime参照・DDLを除去し、0003にDROPを追加。P1-2複製DBからの検証では保持69表100行が一致。V2の付与状態・期限・Outbox・復旧データはFixtureテストでも保持を確認した。原運用DBには未適用。

- 2026-09-11追記：P1-2で `support_tickets` / `ticket_migrations` のRuntime参照・DDLを除去し、0002にDROPを追加。上表は2026-09-10のSnapshotを記録した時点Inventoryとして保持する。P1-2の複製DB検証では保持67表100行が一致し、旧2表の削除・再適用・旧Schema非復活を検証した。原運用DBへの適用を意味しない。

- 原DBは変更していない。Backupと復元先は `data/backups/p0-0910/` に保持しGit対象外。
- 遠隔運用DBやS3 Transcriptはアクセス確認していない。ローカルDBの検証を本番のBackup/Restore成功とは扱わない。
- V1専用行のRuntime自動移行は追加しない。旧Imageへ戻す場合は対応Snapshot復元が必要になる可能性があり、以後の新規データが失われる境界をMigrationごとに記録する。
