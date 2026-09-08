---
feature_id: autorole
title: 初期ロール
keywords: Auto Role default role 参加時 ロール
---

# 初期ロール

サーバーへ参加したMemberへ、指定したRoleを自動付与します。

RoleはDiscordサーバーから選択します。BotにManage Rolesがあり、Botの最上位Roleが付与対象Roleより上にある必要があります。Managed Roleや`@everyone`は付与できません。

## 確認手順

1. 対象Roleを選択して保存します。
2. DiscordのRole一覧でBot Roleを対象より上へ移動します。
3. テストMemberを参加させます。
4. Roleが付かない場合はBotログ、Role階層、Server Members Intentを確認します。

機能を無効化しても、すでに付与したRoleは自動で削除されません。
