import {ChartLine} from 'lucide-react'
import {defineFeature} from '../defaults'

export const feature=defineFeature({id:'insights',category:'community',path:'insights',screenKind:'workspace',
  titleKey:'insights.title',homeTitleKey:'insights.home',icon:ChartLine,namespaces:['insights','common'],
  load:()=>import('./insights/Report'),pages:[{id:'settings',path:'settings',titleKey:'insights.settings',kind:'navigation',access:'manager',load:()=>import('./insights/Settings')}],
})
