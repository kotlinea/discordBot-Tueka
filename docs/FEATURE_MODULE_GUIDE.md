# Tueka 機能モジュール拡張ガイド

この文書は、Discord BotとWebダッシュボードへ新しい機能を追加する際の必須手順です。

## 基本設計

機能はギルド単位の「モジュール」として管理します。モジュールの状態はSQLiteの `guild_modules` にあり、次を持ちます。

- `module_id`: 永続的な機能ID。公開後は変更しない。
- `enabled`: Botが処理を実行するかどうか。新規・未設定モジュールはアプリ上では**無効**として扱われる。
- `settings_json`: 機能固有の設定。無効化しても削除しない。

機能IDは、レジストリ、Cog、URL、保存データで共通です。例: `welcome`。

## 追加時の必須チェックリスト

### 1. 機能をレジストリへ登録

`feature_registry.py` の `FEATURES` に `Feature` を1件追加します。

```python
Feature(
    "auto_reply",                 # module_id: 英小文字・snake_case、以後変更しない
    "community",                 # "community" または "moderation"
    "feature.auto_reply",        # 翻訳キー
    "feature.auto_reply.description",
    "message-circle",            # dashboard/icon_registry.py のSVGアイコンID
    ("reply_channel_id", "text"),  # ダッシュボード設定のフィールド名
)
```

### アイコンをレジストリへ追加

機能カードのアイコンは `dashboard/icon_registry.py` だけで管理します。テンプレートへ条件分岐や任意SVGを追加してはいけません。

1. [All SVG Icons のUIアイコン集](https://allsvgicons.com/collections/ui-icons/) を候補探索の起点にし、既存の **Lucideアウトライン** と同じ24px線画を選ぶ。
2. 採用するアイコンのライセンスを確認する。現在のレジストリはLucide（ISC）のSVGパスをローカルに保持しており、外部サイトのSVGをホットリンクしない。
3. `ICONS` に、意味のあるkebab-case ID・英語の簡潔なラベル・固定の`<path>`／`<rect>`断片を追加する。`<script>`、イベント属性、外部参照、style属性は追加しない。
4. `Feature.icon` にそのIDを指定する。起動時とテストで未登録IDは失敗する。

カードには常に機能見出しがあるため、カード内アイコンは装飾として支援技術から隠します。将来アイコン単独のボタンを作る場合は、レジストリのラベルまたは目的を示す`aria-label`を必ず付けてください。

カテゴリを増やす場合は、`dashboard/app.py` のカテゴリ集約、テンプレート、`dashboard/static/dashboard.js` の日英翻訳を同時に追加します。

### 2. Cogを実装し、有効状態を必ず確認

機能専用Cogを `cogs/<feature>.py` に置き、`config.py` の `extensions` へ追加します。Cogには `GuildStorage(bot.settings.database_path)` を渡してください。

イベントリスナーの最初で有効状態を確認します。

```python
if message.guild is None or message.author.bot:
    return
if not self.storage.module_enabled(message.guild.id, "auto_reply"):
    return
```

スラッシュコマンドも同様です。無効時は処理せず、エフェメラルに案内します。

```python
if not self.storage.module_enabled(interaction.guild.id, "auto_reply"):
    await interaction.response.send_message(
        "この機能は管理者により無効です。", ephemeral=True
    )
    return
```

設定値は `get_module` から取得します。`get_settings` や固定定数を新機能の設定保存先にしないでください。

```python
module = self.storage.get_module(guild_id, "auto_reply")
channel_id = module["settings"].get("reply_channel_id")
```

### 3. ダッシュボードの入力項目・検証を追加

現在の設定フォームは `dashboard/templates/module_settings.html` にあるフィールド名を明示的に扱います。新しいフィールドを追加する場合は、以下をセットで実装します。

1. テンプレートに入力UIを追加する。
2. `save_module_settings` の引数にフォーム値を追加する。
3. 値を型変換・検証する。Discordチャンネル／ロールIDは、`api.guild_resources()` で取得した**対象ギルドのID集合**に含まれることを検証する。
4. `values` 辞書へ追加し、`settings_json` へ保存する。
5. 有効化時に必須なら、未設定を検出して保存を拒否する。

有効化の失敗ではSQLiteを書き換えず、`module_drafts` セッションに入力値を保存して同じ画面へ戻します。この挙動を壊さないでください。設定変更は保存ボタンを押すまでBotへ反映してはいけません。

`fields` が空の機能は、設定なしで有効化できます。必須ではない設定項目がある場合は、`fields` と検証を分けるようレジストリのモデルを拡張してください。すべての `fields` を必須扱いにしないことが重要です。

カテゴリ別の有効状態を持つ機能では、カテゴリを `settings_json` の真偽値として保存し、Cogは**対象カテゴリが無効なら外部API呼び出しや送信前に停止**します。カテゴリのいずれかが有効な場合だけモジュール全体を有効にし、カテゴリごとに必要なBot権限が異なる場合は保存時に個別検証してください。

### 4. 翻訳とUIを追加

画面に表示する文言は `dashboard/static/dashboard.js` の `translations.ja` と `translations.en` の両方へ追加します。

- タイトル: `feature.<id>`
- 説明: `feature.<id>.description`
- 設定ラベル: `field.<field_name>`
- 保存失敗や入力不足の案内文

テンプレートでハードコードせず、`data-i18n` 属性を使います。

```html
<span data-i18n="field.reply_channel">返信チャンネル</span>
```

追加したカードは有効／無効表示、キーボードフォーカス、モバイル幅を確認します。SVGに意味がある場合は、アイコンだけにせずカードの見出しも必ず表示します。

### 5. 権限・安全性を維持

ダッシュボードの変更ルートでは、以下を必ず維持します。

- `authorized(request, guild_id)` によるDiscord Administrator権限の再確認
- CSRFトークンの比較
- ギルドをまたぐリソースIDの拒否
- 不正な `module_id` の404応答
- 失敗時に設定を部分保存しないこと

OAuthトークン、Botトークン、APIキー、セッション秘密鍵をモジュール設定やHTML・ログへ書き込んではいけません。

## 保存データの変更

通常の機能設定は `settings_json` を使用し、SQLiteの列追加は不要です。検索・集計・一意制約が必要な値だけ、専用テーブルを `GuildStorage.initialize()` に追加します。

既存ギルドの設定を変換する場合は、べき等な移行処理を作成し、`app_metadata` に移行済み記録を残します。既存の `migrate_json.py` は旧JSONからの初回移行専用です。これを書き換えて新しいスキーマ移行を混在させないでください。

## テスト要件

機能追加ごとに、少なくとも次を `tests/` へ追加します。

1. レジストリの必須メタデータ・翻訳キー・アイコンが存在する。
2. 新規モジュールは無効で開始する。
3. 有効化／無効化、設定保持、再有効化を確認する。
4. 無効時にCogイベントが副作用を起こさず、コマンドが案内を返す。
5. 必須設定なしの有効化は拒否され、入力下書きが復元される。
6. 他ギルドのチャンネル／ロールID、不正なCSRF、不正なモジュールIDを拒否する。

実行コマンド:

```powershell
python -m unittest discover -s tests -v
python -m compileall -q bot.py config.py storage.py feature_registry.py dashboard cogs tests
```

## 手動確認・リリース

1. ローカルでBotとダッシュボードを起動する。
2. 管理者アカウントでログインし、対象ギルドを選択する。
3. 初期状態が無効であることを確認する。
4. 必須設定なしの有効化が拒否され、入力値が残ることを確認する。
5. 保存後、Botの実イベントとスラッシュコマンドが有効化状態に従うことを確認する。
6. 無効化後も設定が残り、再有効化で復元されることを確認する。
7. 日本語・英語、light・dark・system、狭い画面幅を確認する。
8. VPSではBotとダッシュボードを個別に再起動し、`journalctl` で例外がないことを確認する。

## 追加前の最終確認

- [ ] IDは永続的で、既存IDを変更・再利用していない。
- [ ] 無効時のイベントとコマンドの両方を停止している。
- [ ] 保存前にBotへ反映されない。
- [ ] 有効化失敗時に入力を失わず、確定データも変えない。
- [ ] 日英のUI文言、SVG、モバイル表示を追加した。
- [ ] セキュリティ・自動テスト・手動確認を完了した。
