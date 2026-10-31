import { ChartBar } from 'lucide-react'
import { defineFeature } from '../defaults'
export const feature=defineFeature({id:'advanced_polls',category:'engagement',path:'modules/advanced_polls',screenKind:'workspace',
 titleKey:'polls.title',homeTitleKey:'polls.list',icon:ChartBar,namespaces:['polls','common'],access:'delegated',
 load:()=>import('./polls/Polls'),pages:[{id:'settings',path:'settings',titleKey:'polls.settings',kind:'navigation',access:'delegated',load:()=>import('./polls/Settings')}]})
