---
feature_id: tickets
title: サポートチケット
keywords: Ticket Panel Form Staff Claim Close Transcript S3 Outbox private thread
---

# サポートチケット

Ticketは`Panel Message → Panel → Form → Ticket → Staff対応 → Close → Feedback / Transcript`として処理されます。Discordボタン、コマンド、Dashboardは同じTicket Serviceを使用します。


## 6タブEditor

1. **チケット設定**：Mention Role、Team、Transcript Channel、Mode、Cooldown、Category、User上限、操作Button、退出Form、命名規則
2. **パネル**：配置Message、Title、Description、Color、Channel、Button Style／Text／Emoji、画像
3. **ようこそメッセージ**：Title、Description、Author、Image、Thumbnail、Footer、Timestamp、最大25 Fields
4. **チケットの許可**：Embed、添付、外部Emoji／Sticker、Voice MessageなどChannel権限
5. **アクセス制御**：Role単位の許可／拒否。拒否一致を優先
6. **サポート時間**：IANA Timezone、24時間受付、曜日別の時間帯

全変更はDraftです。保存時にPanelとPanel Messageのrevision、Discordリソース所属、文字数、URL、権限をまとめて検証します。

## Channel ModeとThread Mode

| 項目 | Channel | Private Thread |
| --- | --- | --- |
| 作成先 | Category内の専用Channel | 親Channel内のPrivate Thread |
| Claim / Staff Notes | 対応 | Join / On-Call方式 |
| Close | Transcript確定後に即時削除 | Locked＋Archived |
| Reopen | 不可 | 手動削除前なら可能 |
| 権限 | Ticket用Overwrite | 親Channelの権限を継承 |

## 作成判定

機能有効 → Blacklist → Access Rule → Support Hours → Guild上限 → User上限 → Cooldown → Form → Discord権限 → DB予約・Discord作成の順です。Interaction IDで二重作成を防ぎます。

Staffは上限とCooldownの対象外です。Support Hours外では次回受付時刻を表示します。

## 対応とClose

Channel ModeではClaim、Unclaim、Transfer、Staff Notesを利用できます。回答待ちへ移すと専用Categoryへ移動し、作成者の返信で元Categoryへ戻ります。Discord移動失敗時はDB状態を確定しません。

Close Requestは24時間有効です。理由付きCloseは理由入力を必須にできます。Thread ModeはArchive後にReopenできます。

## Transcript

Form回答、全Message、編集・削除状態、Staff操作、Close理由、添付Metadataを時系列で生成します。本文は保存用の鍵で暗号化します。

S3互換設定があればアップロード後の整合性確認に成功したS3を正本にし、失敗時は暗号化Localへ保存して再送します。保持期間は既定365日、1～3650日です。添付は1件25MB、Ticket合計100MBまでです。

閲覧者は作成者本人、Manage Guild保持者、Ticket管理者、担当Teamに限定されます。任意HTMLや任意Mentionは送信しません。

## テンプレート変数

Welcomeは`{ticket_number}`、`{user}`、`{username}`、`{user_id}`、`{panel}`、`{team}`を使用できます。Channel名は`{number}`、`{username}`、`{user_id}`、`{panel}`を使用できます。

## 必要権限

Manage Channels、Manage Threads、Create Private Threads、Send Messages in Threads、Read Message History、Manage Messages、Embed Links、Attach FilesをModeに応じて確認してください。
