import { defineConfig } from 'vitepress'
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
function sidebar(lang: string) {
  const prefix = lang ? '/en' : ''
  return ['guide', 'dashboard', 'features', 'social', 'reference', 'troubleshooting'].map(group => ({
    text: lang ? ({ guide: 'Get started', dashboard: 'Dashboard', features: 'Features', social: 'Social', reference: 'Reference', troubleshooting: 'Troubleshooting' } as Record<string, string>)[group] : ({ guide: 'はじめに', dashboard: 'ダッシュボード', features: '機能', social: '通知・ソーシャル', reference: 'リファレンス', troubleshooting: '困ったときは' } as Record<string, string>)[group],
    items: readdirSync(join(__dirname, '..', lang, group)).filter(name => name.endsWith('.md')).sort().map(name => {
      const content = readFileSync(join(__dirname, '..', lang, group, name), 'utf8')
      return { text: content.match(/^# (.+)$/m)?.[1] || name, link: `${prefix}/${group}/${name === 'index.md' ? '' : name.slice(0, -3)}` }
    })
  }))
}
export default defineConfig({
  title: 'Tueka Docs', description: 'Member and server manager guides', base: '/docs/', cleanUrls: true,
  lastUpdated: true, ignoreDeadLinks: false,
  locales: {
    root: { label: '日本語', lang: 'ja-JP', themeConfig: { sidebar: sidebar(''), nav: [
      { text: 'はじめに', link: '/guide/getting-started' }, { text: 'Dashboard操作', link: '/dashboard/' },
      { text: '全コマンド', link: '/reference/commands' }
    ] } },
    en: { label: 'English', lang: 'en-US', link: '/en/', themeConfig: { sidebar: sidebar('en'), nav: [
      { text: 'Get started', link: '/en/guide/getting-started' }, { text: 'Dashboard guide', link: '/en/dashboard/' },
      { text: 'All commands', link: '/en/reference/commands' }
    ] } }
  },
  themeConfig: {
    siteTitle: 'Tueka Docs', search: { provider: 'local', options: { locales: { root: { translations: { button: { buttonText: 'ドキュメントを検索', buttonAriaLabel: 'ドキュメントを検索' } } } } } },
    outline: { level: [2, 3] }, externalLinkIcon: true
  }
})
