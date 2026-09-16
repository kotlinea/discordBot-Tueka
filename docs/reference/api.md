# API

Swagger UIは `/api/docs`、OpenAPI JSONは `/api/openapi.json` です。Dashboard APIは `/api/v1` 配下です。このバージョンは廃止済みDashboard V1とは別で、Router分割後もURLを維持します。

## 認証とCSRF

Read APIにもDiscord OAuth Sessionが必要です。CookieのSession IDに対応するサーバー側Sessionが存在し、有効期限内であることを検証します。更新はSessionに加えて `X-CSRF-Token` Headerを検証し、対象Guildの管理権限をキャッシュなしで確認します。公開Social OAuth開始のフォームは `csrf_token` を同じ検証へ渡します。

TicketのInbox・返信・操作は管理者または担当TeamのStaffに限定します。TeamにユーザーIDが登録されていてもGuild所属が失われたユーザーには許可しません。Transcript/添付は申請者本人も閲覧できます。Ticket設定の変更は管理者権限が必要です。読み取り専用Panel previewは従来どおり管理者認可のみで、保存は行いません。

## エラーと競合

Domainエラーの通常の応答例は次の形です。HTTPステータスは本文とは別に返ります。

```json
{
  "detail": {
    "code": "revision_conflict",
    "message": "別の管理者が設定を更新しました。"
  }
}
```

- `401`：未認証、Session不在・期限切れ
- `403`：CSRF不一致、Guild管理権限またはTicket Staff/担当Team権限がない
- `404`：対象が存在しない、別Guild、期限切れTranscriptなど
- `409`：revision競合、公開復旧待ちなどDomain状態の競合
- `422`：入力、Discord Resource、権限、組み合わせが無効

入力エラーの追加情報は現行Domainにより `fields` または `errors` です。FastAPI自身のパス/Query検証エラーは `detail` 配列、対象不在の一部は文字列です。全API共通の新しい応答Schemaに統一したものではありません。

revisionは各応答の値を次の更新へ渡してください。Reaction Roles削除には `If-Match` が必要で、省略または古い値は409です。Social削除とModerationの対象操作にも現行のrevision検査があります。共通Header検査では整数と引用符で囲んだ整数を受け付け、解釈不能な値は422 `revision_invalid` を返します。409後は再読込して変更を確認してください。

## 実装と契約の検証

Domain Routerは `dashboard/api/`、合成入口は `dashboard/api_v1.py` です。Repository/ServiceはContextから明示的に渡し、認証・CSRF・Resource・競合エラーを共通化しています。構造の対応表は[アーキテクチャ](./architecture)を参照してください。

分割前のOpenAPIと199ケースの認証・認可・CSRF応答を固定し、Contract testで比較します。さらに保存・再読込・競合・別Guild・Bot権限不足・Ticketファイル閲覧・Session失効・複数アプリの分離をHTTP経由で検証します。ID・Pagination・日時や型生成の横断整理は、Frontendと同時に行う次の実行単位です。
