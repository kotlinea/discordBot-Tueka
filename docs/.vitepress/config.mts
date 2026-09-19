import { defineConfig } from 'vitepress'

const featureSidebar = [
  { text: 'Moderation', items: [
    { text: '概要', link: '/features/moderation' }, { text: 'AutoMod', link: '/features/automod' },
    { text: 'Anti-Spam', link: '/features/anti-spam' }, { text: 'Anti-Raid', link: '/features/anti-raid' },
    { text: 'Warnings / Infractions', link: '/features/infractions' }, { text: 'Moderation Actions', link: '/features/moderation-actions' },
    { text: 'Moderation Logs', link: '/features/moderation-logs' }, { text: 'サーバーログ', link: '/features/audit-log' },
    { text: 'Trust Score', link: '/features/trust-score' },
  ]},
  { text: 'Community', items: [
    { text: '入退室', link: '/features/welcome' }, { text: '初期ロール', link: '/features/autorole' },
    { text: 'レベリング', link: '/features/leveling' }, { text: 'リアクションロール', link: '/features/reaction-roles' },
    { text: '一時的な音声チャンネル', link: '/features/temporary-voice' }, { text: 'チケット', link: '/features/tickets' },
    { text: 'ライブ統計', link: '/features/live-stats' },
  ]},
  { text: 'Engagement', items: [
    { text: '拡張投票', link: '/features/polls' }, { text: 'Suggestions', link: '/features/suggestions' }, { text: 'ミニゲーム', link: '/features/minigames' },
  ]},
]

export default defineConfig({
  title: 'Tueka Docs',
  description: 'Tuekaの設定、機能、運用、復旧手順',
  base: '/docs/',
  cleanUrls: true,
  // Development plans and verification logs are repository artifacts, not public guides.
  srcExclude: ['EXECUTION_PLAN.md', 'PROGRESS0910.md', 'TESTING.md', 'inventory/**'],
  lastUpdated: true,
  ignoreDeadLinks: false,
  locales: {
    root: { label: '日本語', lang: 'ja-JP', title: 'Tueka Docs' },
    en: { label: 'English', lang: 'en-US', title: 'Tueka Docs', link: '/en/' },
  },
  themeConfig: {
    siteTitle: 'Tueka Docs',
    search: { provider: 'local', options: { locales: { root: { translations: { button: { buttonText: 'ドキュメントを検索', buttonAriaLabel: 'ドキュメントを検索' }, modal: { noResultsText: '見つかりませんでした', resetButtonTitle: '検索を消去', footer: { selectText: '選択', navigateText: '移動', closeText: '閉じる' } } } } } } },
    nav: [
      { text: 'はじめに', link: '/guide/getting-started' }, { text: '機能', link: '/features/moderation' },
      { text: 'ソーシャル', link: '/social/' }, { text: '運用', link: '/operations/' },
      { text: 'リファレンス', link: '/reference/commands' }, { text: 'Dashboard', link: '/servers' },
    ],
    sidebar: {
      '/guide/': [{ text: 'はじめに', items: [
        { text: 'Tuekaについて', link: '/guide/' }, { text: '導入する', link: '/guide/getting-started' },
        { text: '必要な権限とIntents', link: '/guide/permissions' }, { text: '最初のサーバー設定', link: '/guide/first-server' },
      ]}],
      '/dashboard/': [{ text: 'ダッシュボード', items: [
        { text: '基本操作', link: '/dashboard/' }, { text: '保存と競合', link: '/dashboard/saving' }, { text: '権限診断', link: '/dashboard/permissions' },
      ]}],
      '/features/': featureSidebar,
      '/social/': [{ text: '通知・ソーシャル', items: [
        { text: '概要', link: '/social/' }, { text: 'YouTube', link: '/social/youtube' }, { text: 'Twitch', link: '/social/twitch' },
        { text: 'X', link: '/social/x' }, { text: 'TikTok', link: '/social/tiktok' }, { text: 'Instagram', link: '/social/instagram' },
        { text: 'Worker運用', link: '/social/worker' },
      ]}],
      '/operations/': [{ text: '運用', items: [
        { text: '構成と起動', link: '/operations/' }, { text: 'Windows', link: '/operations/windows' }, { text: 'Linux / VPS', link: '/operations/linux' },
        { text: 'バックアップと復元', link: '/operations/backup' }, { text: '更新とロールバック', link: '/operations/upgrade' },
        { text: 'DB Migration', link: '/operations/migrations' },
        { text: '本番Image', link: '/operations/container' },
        { text: '環境別Compose', link: '/operations/compose' },
        { text: '監視と障害対応', link: '/operations/monitoring' },
        { text: 'Stage受入', link: '/operations/stage-acceptance' },
        { text: 'セキュリティ', link: '/operations/security' },
      ]}],
      '/reference/': [{ text: 'リファレンス', items: [
        { text: 'コマンド', link: '/reference/commands' }, { text: '環境変数', link: '/reference/environment' },
        { text: 'API', link: '/reference/api' }, { text: 'アーキテクチャ', link: '/reference/architecture' },
        { text: '機能追加', link: '/reference/extending' }, { text: '用語集', link: '/reference/glossary' },
      ]}],
      '/troubleshooting/': [{ text: 'トラブルシューティング', items: [{ text: '症状から探す', link: '/troubleshooting/' }] }],
      '/en/': [{ text: 'English', items: [
        { text: 'Overview', link: '/en/' }, { text: 'Getting started', link: '/en/getting-started' },
        { text: 'Features', link: '/en/features' }, { text: 'Operations', link: '/en/operations' }, { text: 'Troubleshooting', link: '/en/troubleshooting' },
      ]}],
    },
    outline: { level: [2, 3], label: 'このページ' },
    docFooter: { prev: '前のページ', next: '次のページ' },
    lastUpdated: { text: '最終更新' },
    returnToTopLabel: 'ページ上部へ戻る',
    sidebarMenuLabel: 'メニュー',
    darkModeSwitchLabel: 'カラースキーム',
    langMenuLabel: '言語',
    externalLinkIcon: true,
  },
  head: [
    ['meta', { name: 'theme-color', content: 'oklch(50% .19 255)' }],
    ['meta', { name: 'robots', content: 'index,follow' }],
  ],
})
