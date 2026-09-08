# API

Swagger UIは`/api/docs`、OpenAPI JSONは`/api/openapi.json`です。Dashboard APIは`/api/v1`配下です。

## 認証とCSRF

Read APIにもDiscord OAuth Sessionが必要です。更新はSessionに加えてCSRF Headerを検証し、対象GuildのManage Guild権限を再確認します。

## エラー

```json
{
  "status": 422,
  "code": "validation_failed",
  "detail": "入力を確認してください。",
  "errors": [
    { "path": "actions.0.duration", "message": "期間が範囲外です。" }
  ]
}
```

- `401`：ログインが必要
- `403`：Guild管理権限またはTicket Staff権限がない
- `404`：対象が存在しない、または閲覧不可
- `409`：revision競合
- `422`：入力、Discord Resource、権限、組み合わせが無効

更新Payloadのrevisionを省略したり、409後に古い値を再送したりしないでください。
