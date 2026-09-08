---
feature_id: automod
title: AutoMod
keywords: 禁止ワード 正規表現 URL ドメイン Discord招待 Safe Browsing 絵文字 スタンプ
---

# AutoMod

メッセージ内容を検査し、削除、Warning、通知、Timeoutなどを組み合わせます。時間窓の連投対策は[Anti-Spam](./anti-spam)を使用します。

## Trigger

| Trigger | 主な設定 | 注意点 |
| --- | --- | --- |
| keyword | キーワード、ワイルドカード、許可語 | Unicode正規化後に評価 |
| regex | パターン | タイムアウト付き。保存時にも検証 |
| domain | 許可／拒否Domain | IDNを正規化し完全なDomain境界で判定 |
| discord_invite | 招待リンク | Discord招待URLだけを判定 |
| safe_browsing | URL | API未設定・障害時はfail-open |
| phishing_link | 表示名と遷移先 | 不一致やフィッシング表記を検査 |
| caps | 大文字率、最小文字数 | 短文を除外可能 |
| emoji_sticker_rate | Emoji／Sticker数 | 1投稿または時間窓で判定 |
| media_only | 対象Channel | 添付・Embedを含まない投稿を検知 |
| honeypot | 対象Channel | 投稿自体を検知 |

## 適用範囲と例外

Whitelist方式は選択した対象だけに適用し、Blacklist方式は選択した対象を除外します。同じ対象を許可と拒否へ同時登録する構成は保存できません。Role、User、Channel、Categoryを設定できます。

## Action

Actionは上から順に実行します。削除済みメッセージ、DM拒否、権限不足などで失敗しても、実行可能な後続Actionは継続し、結果をイベントへ保存します。

利用できる処置は削除、Warning／points、公開通知、DM、モデレーター通知、ログ、Timeout、Kick、Ban、Tempbanです。テンプレートActionでは画面に表示される変数だけを使用してください。

## 正規表現の注意

複雑なパターンは保存時に拒否されることがあります。巨大な繰り返しや曖昧な入れ子を避け、プレビューで一致・不一致とタイムアウトを確認します。
