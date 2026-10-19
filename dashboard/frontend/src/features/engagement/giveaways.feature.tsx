import {Trophy} from 'lucide-react'
import {defineFeature,loadModuleSettings} from '../defaults'
export const feature=defineFeature({id:'giveaways',category:'engagement',path:'giveaways',screenKind:'workspace',titleKey:'giveaways.title',homeTitleKey:'giveaways.list',icon:Trophy,namespaces:['giveaways','common'],load:()=>import('./giveaways/Campaigns'),pages:[{id:'settings',path:'settings',titleKey:'giveaways.settings',kind:'navigation',access:'manager',load:loadModuleSettings}]})
