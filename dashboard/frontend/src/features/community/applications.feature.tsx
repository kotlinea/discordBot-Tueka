import { ClipboardList } from 'lucide-react'
import { defineFeature, loadModuleSettings } from '../defaults'
export const feature = defineFeature({id:'applications',category:'community',presentationCategory:'server_operations',
  path:'applications',screenKind:'workspace',titleKey:'applications.title',homeTitleKey:'applications.forms',icon:ClipboardList,
  namespaces:['applications','common'],load:()=>import('./applications/Forms'),
  pages:[{id:'review',path:'review',titleKey:'applications.review',kind:'navigation',access:'manager',load:()=>import('./applications/Review')},
    {id:'settings',path:'settings',titleKey:'applications.settings',kind:'navigation',access:'manager',load:loadModuleSettings}],
})
