---
feature_id: tiktok_updates
title: TikTok通知
keywords: TikTok Display API yt-dlp best effort poll
---

# TikTok通知

新規投稿と公開ライブ状態を定期確認します。

OAuth済み本人アカウントでは公式Display APIを優先します。任意の公開アカウントは、Workerが固定形式URLを生成し、シェルを介さず`yt-dlp`を実行します。動画本体はダウンロードしません。

::: warning ベストエフォート
任意アカウント監視は非公式です。TikTokの公開ページ仕様、地域制限、Bot対策の変更により停止することがあります。
:::

投稿確認は既定120秒、ライブ確認は60秒を基準に、Jitter、同時実行上限、指数Backoffを適用します。Timeoutや連続失敗はTikTok AdapterのCircuit Breakerだけに作用します。
