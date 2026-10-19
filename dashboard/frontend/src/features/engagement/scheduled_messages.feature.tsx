import { CalendarClock } from 'lucide-react'
import { defineFeature, loadModuleSettings } from '../defaults'
export const feature=defineFeature({id:'scheduled_messages',category:'engagement',path:'schedules',screenKind:'workspace',
  titleKey:'scheduling.title',homeTitleKey:'scheduling.list',icon:CalendarClock,namespaces:['scheduling','common'],
  load:()=>import('./scheduling/Schedules'),fields:{retention_days:{labelKey:'scheduling.retention'}},
  pages:[{id:'settings',path:'settings',titleKey:'scheduling.settings',kind:'navigation',access:'manager',load:loadModuleSettings}]})
