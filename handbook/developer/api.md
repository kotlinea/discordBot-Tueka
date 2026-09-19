# API

Swagger UIは `/api/docs`、OpenAPI JSONは `/api/openapi.json` です。Dashboard APIは `/api/v1` 配下です。このバージョンは廃止済みDashboard V1とは別で、Router分割後もURLを維持します。

## 認証とCSRF

Read APIにもDiscord OAuth Sessionが必要です。CookieのSession IDに対応するサーバー側Sessionが存在し、有効期限内であることを検証します。更新はSessionに加えて `X-CSRF-Token` Headerを検証し、対象Guildの管理権限をキャッシュなしで確認します。公開Social OAuth開始のフォームは `csrf_token` を同じ検証へ渡します。

TicketのInbox・返信・操作は管理者または担当TeamのStaffに限定します。TeamにユーザーIDが登録されていてもGuild所属が失われたユーザーには許可しません。Transcript/添付は申請者本人も閲覧できます。Ticket設定の変更は管理者権限が必要です。読み取り専用Panel previewは従来どおり管理者認可のみで、保存は行いません。

## エラーと競合

登録済みの `/api/v1` Routeは、認証・認可・Domain・パス/Query/JSON入力のエラーを次の形に統一します。HTTPステータスは本文とは別に返ります。公開HTML画面とOAuth RedirectはこのJSON契約の対象外です。

```json
{
  "detail": {
    "code": "revision_conflict",
    "message": "別の管理者が設定を更新しました。",
    "errors": []
  }
}
```

- `401`：未認証、Session不在・期限切れ
- `403`：CSRF不一致、Guild管理権限またはTicket Staff/担当Team権限がない
- `404`：対象が存在しない、別Guild、期限切れTranscriptなど
- `409`：revision競合、公開復旧待ちなどDomain状態の競合
- `422`：入力、Discord Resource、権限、組み合わせが無効

`detail.errors` は常に配列です。項目別エラーは `{ "path": "settings.form_fields.0.label", "message": "..." }` の形です。該当項目がない場合は空配列です。旧 `fields` や文字列の例外はHTTP境界でこの形式へ変換します。検証失敗の応答には送信した生の入力値を含めません。FrontendはHTTPステータス・code・項目エラーを保持し、保存失敗時も編集内容を維持します。

revisionは各応答の値を次の更新へ渡してください。Reaction Roles削除には `If-Match` が必要で、省略または古い値は409です。Social削除とModerationの対象操作にも現行のrevision検査があります。共通Header検査では整数と引用符で囲んだ整数を受け付け、解釈不能な値は422 `revision_invalid` を返します。409後は再読込して変更を確認してください。

## 実装と契約の検証

Domain Routerは `dashboard/api/`、合成入口は `dashboard/api_v1.py` です。Repository/ServiceはContextから明示的に渡し、認証・CSRF・Resource・競合エラーを共通化しています。構造の対応表は[アーキテクチャ](architecture.md)を参照してください。

分割前のOpenAPI 59パスと199ケースの認証・認可・CSRF応答を固定し、URL・操作・認可境界をContract testで比較します。P2-6のSchema追加、エラー統一、一覧の `next` 追加はFrontendと同時に適用した意図的な契約変更です。元のFixtureは書き換えず、比較側でこの変換を明示しています。保存・再読込・競合・別Guild・Bot権限不足・Ticketファイル閲覧・Session失効・複数アプリの分離もHTTP経由で検証します。


## 型・ID・日時・一覧

- Guild、User、Role、Channel、Discord MessageなどのSnowflakeはJSON文字列です。JavaScriptの数値へ変換しないでください。Ticket・Panel・Form・Team・Case・Outbox等の内部DB IDとrevisionは整数です。Ticketのform_id、team_id、panel_id、panel_message_id等も整数へ揃えています。
- 保存済みイベントのcreated_at、updated_at、期限等の時刻はUTCのUnix秒です。画面で表示用に変換するときだけ1000倍します。週次ScheduleはIANA timezoneと曜日別の `HH:mm` を使い、絶対時刻とは区別します。
- 一覧Envelope `Items[T]` は `items` と `next` を返します。次ページがない、または全件取得の一覧では `next: null` です。ページングを提供するRouteでは既存の整数Cursorを維持します。設定・概要・統計は個別のSchemaです。
- 添付取得は認可後に `application/octet-stream` を返し、生成クライアントでは `Blob` として受け取ります。204の削除応答は本文なしです。
- Moduleの可変設定、Moderation Triggerの種類別設定、Outbox payload等はJSONオブジェクトとして保持します。生成型では `Record<string, unknown>` とし、Domainの正規化・組合せ検証が責任を持ちます。

## SchemaからFrontendへの生成

`dashboard/api/schemas/` が公開DTOと入力制約を定義します。`body.py` は同じ入力ModelからOpenAPIを構築し、実際のJSONも検証します。作成・更新の部分入力は未指定の項目をDomainへ渡さず、既定値・組合せ・Guild Resource検査はDomainとRouterで行います。明示的なnullはnullable項目に限ります。

Python 3.13の依存導入済み環境で、Repositoryルートから実行します。

```sh
python scripts/generate_api.py
python scripts/generate_api.py --check
```

生成物は `dashboard/api/openapi.json` と `dashboard/frontend/src/generated/api.ts` です。生成時は一時DBにMigrationを適用し、実Routerから公開契約を取り出します。運用DB、環境変数、Discord接続は不要です。生成物を直接編集せず、Schemaを変更して再生成してください。CIは差分検査で更新漏れを失敗にします。

Frontendの `request` と `encodeBody` は生成された操作別の応答型・入力型を使用します。Form・Embed等の文字数や件数の上限は生成された `constraints` を参照します。ブラウザー側の制約だけに頼らず、API側でも同じ項目制約とDomainの検証を実行します。
