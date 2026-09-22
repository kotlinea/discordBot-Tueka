import { useTranslation } from 'react-i18next'
import type { FeatureScreenProps } from './contracts'
import { ModuleSettings } from '../components/feature/ModuleSettings'
import { SettingField } from '../components/forms/SettingField'

/** Composition only: field presentation belongs to the selected feature definition. */
export default function DefaultSettings({ features, definition }: FeatureScreenProps) {
  const { t } = useTranslation([...(definition?.namespaces ?? ['common'])])
  return <ModuleSettings feature={features.find(item => item.id === definition?.id)} renderField={props => {
    const field = definition?.fields?.[props.name]
    return <SettingField {...props} {...field} label={field ? t(field.labelKey) : props.name}/>
  }}/>
}
