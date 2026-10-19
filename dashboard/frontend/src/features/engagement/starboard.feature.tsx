import {Star} from 'lucide-react'
import {defineFeature,loadModuleSettings} from '../defaults'
export const feature=defineFeature({id:'starboard',category:'engagement',path:'starboard',screenKind:'workspace',titleKey:'starboard.title',homeTitleKey:'starboard.list',icon:Star,namespaces:['starboard','common'],load:()=>import('./starboard/Boards'),pages:[{id:'settings',path:'settings',titleKey:'starboard.settings',kind:'navigation',access:'manager',load:loadModuleSettings}]})
