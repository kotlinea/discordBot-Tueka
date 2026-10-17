import { Mail } from 'lucide-react'
import { defineFeature, loadModuleSettings } from '../defaults'
export const feature=defineFeature({id:'appeals',category:'moderation',path:'appeals',screenKind:'workspace',
  titleKey:'appeals.title',homeTitleKey:'appeals.inbox',icon:Mail,namespaces:['appeals','common'],
  load:()=>import('./appeals/Inbox'),fields:{retention_days:{labelKey:'appeals.retention'}},
  pages:[{id:'settings',path:'settings',titleKey:'appeals.settings',kind:'navigation',access:'manager',load:loadModuleSettings}]})
