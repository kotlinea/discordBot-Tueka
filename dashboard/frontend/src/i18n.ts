import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import ja from './locales/ja'
import en from './locales/en'
void i18n.use(initReactI18next).init({ resources: { ja, en }, lng: 'ja', fallbackLng: 'ja', interpolation: { escapeValue: false } })
export default i18n

