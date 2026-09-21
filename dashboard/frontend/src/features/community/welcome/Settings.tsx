import { useTranslation } from 'react-i18next'
import type { FeatureScreenProps } from '../../contracts'
import { ModuleSettings } from '../../../components/feature/ModuleSettings'
import { SettingField } from '../../../components/forms/SettingField'

const variables = ['user', 'username', 'displayname', 'server', 'membercount']

export default function WelcomeSettings({ features }: FeatureScreenProps) {
  const { t } = useTranslation('common')
  const feature = features.find(item => item.id === 'welcome')
  return <ModuleSettings feature={feature} title={t('welcome.title')} description={t('welcome.description')} renderField={props => <SettingField {...props}
    label={t(`welcome.fields.${props.name}`)}
    options={props.name.endsWith('_format') ? [{ value: 'text', label: t('welcome.text') }, { value: 'embed', label: t('welcome.embed') }] : undefined}
    template={props.name.endsWith('_content') ? { variables, maxLength: 4096, multiline: true } : undefined}
  />}/>
}
