import DefaultTheme from 'vitepress/theme'
import { defineComponent, h, onMounted, ref } from 'vue'
import '@fontsource/space-grotesk/600.css'
import '@fontsource/space-grotesk/700.css'
import '@fontsource/noto-sans-jp/400.css'
import '@fontsource/noto-sans-jp/600.css'
import '@fontsource/geist-mono/400.css'
import './custom.css'

const AppearanceControl = defineComponent({
  setup() {
    const value = ref('precision')
    onMounted(() => {
      value.value = localStorage.getItem('tueka.docs.appearance') || 'precision'
      document.documentElement.dataset.appearance = value.value
      const syncScheme = () => { document.documentElement.dataset.colorScheme = document.documentElement.classList.contains('dark') ? 'dark' : 'light' }
      syncScheme()
      new MutationObserver(syncScheme).observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
    })
    const update = (event: Event) => {
      value.value = (event.target as HTMLSelectElement).value
      document.documentElement.dataset.appearance = value.value
      localStorage.setItem('tueka.docs.appearance', value.value)
    }
    return () => h('label', { class: 'appearance-control' }, [
      h('span', { class: 'visually-hidden' }, '外観'),
      h('select', { value: value.value, 'aria-label': '外観', onChange: update }, [
        h('option', { value: 'precision' }, 'Precision'),
        h('option', { value: 'community' }, 'Community'),
        h('option', { value: 'atmosphere' }, 'Atmosphere'),
      ]),
    ])
  },
})

// This route belongs to the Dashboard, outside VitePress's /docs/ base.
const dashboardLink = () => h('a', { href: '/servers', target: '_self', class: 'dashboard-link' }, 'Dashboard')

export default {
  extends: DefaultTheme,
  Layout: () => h(DefaultTheme.Layout, null, {
    'nav-bar-content-after': () => h('div', { class: 'appearance-top' }, [dashboardLink(), h(AppearanceControl)]),
    'nav-screen-content-after': () => h('div', { class: 'appearance-mobile' }, [dashboardLink(), h(AppearanceControl)]),
  }),
}
