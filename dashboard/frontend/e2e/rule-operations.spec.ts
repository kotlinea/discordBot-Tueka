import { test, expect, type Page } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import ja from '../src/locales/ja'
import en from '../src/locales/en'
import type { Rule } from '../src/types'

const triggers: Record<string,string>={automod:'keyword',anti_spam:'message_rate',anti_raid:'join_rate'}
const defaults=(family:string,trigger=triggers[family]):Rule=>({family,event_type:family==='anti_raid'?'member_join':'message_create',name:'Default',enabled:false,mode:'monitor',priority:100,stop_on_match:false,trigger_type:trigger,trigger_config:trigger==='keyword'?{keywords:[],allow_list:[],match:'wildcard'}:{limit:6,window_seconds:10},conditions:{},exemptions:{},actions:[{type:'log'}]})
async function fixture(page:Page,locale:string,family:string) {
  const state={items:[] as Rule[],posts:0,puts:0,fail:0,failSave:0,missing:false,permissions:'8',templateFail:false,pause:null as Promise<void>|null}
  const feature=(id:string)=>({id,category:'moderation',parent:id==='moderation'?null:'moderation',title:id,description:id,enabled:id!=='moderation',settings:{},fields:[],required_fields:[],required_bot_permissions:[],missing_permissions:[],revision:1})
  await page.route('**/api/v1/**',async route=>{
    const path=new URL(route.request().url()).pathname.replace('/api/v1',''); const method=route.request().method()
    if(path==='/session')return route.fulfill({json:{user:{id:'20',name:'Manager'},csrf_token:'csrf',preferences:{locale,appearance:'precision',color_scheme:'light',revision:1}}})
    if(path==='/guilds')return route.fulfill({json:{items:[{id:'1',name:'U5 Guild',access:'manager'}]}})
    if(path.endsWith('/features'))return route.fulfill({json:{items:['moderation',...Object.keys(triggers)].map(feature)}})
    if(path.endsWith('/resources'))return route.fulfill({json:{channels:state.missing?[]:[{id:'123456789012345678',name:'Alpha',type:0},{id:'123456789012345679',name:'Beta',type:0}],roles:[],emojis:[],bot_permissions:state.permissions}})
    if(path.includes('/templates/'))return state.templateFail?route.fulfill({status:503,json:{detail:{message:'Template unavailable'}}}):route.fulfill({json:defaults(family,path.split('/').at(-1))})
    if(path.endsWith('/rules/state')){
      state.puts++;const body=route.request().postDataJSON()
      if(state.pause)await state.pause
      if(state.fail){const status=state.fail;state.fail=0;if(status===409)state.items[1]={...state.items[1],revision:state.items[1].revision!+1};return route.fulfill({status,json:{detail:{code:status===409?'revision_conflict':'denied',message:`Failure ${status}`}}})}
      expect(body.items).toHaveLength(2)
      for(const selected of body.items)expect(state.items.find(item=>item.id===selected.id)?.revision).toBe(selected.revision)
      state.items=state.items.map(item=>body.items.some((selected:{id:number})=>item.id===selected.id)?{...item,enabled:body.enabled,revision:item.revision!+1}:item)
      return route.fulfill({json:{items:state.items,next:null}})
    }
    if(path.endsWith('/rules')){
      if(method==='POST'){
        const body=route.request().postDataJSON();expect(body).not.toHaveProperty('id');expect(body).not.toHaveProperty('revision');expect(body.enabled).toBe(false)
        if(state.failSave){const status=state.failSave;state.failSave=0;return route.fulfill({status,json:{detail:{code:'save_failed',message:`Save ${status}`}}})}
        state.posts++;const value={...body,id:state.posts,revision:1,priority:state.posts*10,guild_id:'1'};state.items.push(value)
        return route.fulfill({status:201,json:value})
      }
      return route.fulfill({json:{items:state.items,trigger_types:family==='anti_spam'?['message_rate','duplicate']:[triggers[family]],next:null}})
    }
    return route.fulfill({json:{items:[],next:null}})
  })
  return state
}

for(const locale of ['ja','en'] as const)for(const family of Object.keys(triggers))test(`rule lifecycle ${family} ${locale}`,async({page},testInfo)=>{
  const copy=locale==='ja'?ja:en;const words=copy.moderation.operations;const labels=copy.moderation.rule
  const state=await fixture(page,locale,family)
  await page.goto(`/servers/1/moderation/${family}`)
  await page.getByRole('link',{name:copy.common.common.create,exact:true}).first().click()
  await page.getByLabel(labels.name,{exact:true}).fill('First')
  if(family==='automod')await page.getByLabel(words.keywords,{exact:true}).fill('blocked')
  await page.getByRole('button',{name:new RegExp(labels.scope)}).click()
  const channel=page.getByRole('heading',{name:words.channel,exact:true}).locator('..').locator('..')
  await channel.getByRole('button',{name:copy.common.common.onlySelected,exact:true}).click()
  await channel.getByRole('checkbox',{name:'Alpha',exact:true}).check()
  await page.getByRole('region').filter({has:page.getByRole('button',{name:copy.common.common.save,exact:true})}).getByRole('button',{name:copy.common.common.save,exact:true}).click()
  await expect.poll(()=>state.posts).toBe(1)
  await expect(page.getByText('First',{exact:true})).toBeVisible()
  const original=structuredClone(state.items[0])
  await page.getByRole('link',{name:words.clone,exact:true}).click()
  await expect(page.getByLabel(labels.name,{exact:true})).toHaveValue(words.cloneName.replace('{{name}}','First'))
  expect(state.posts).toBe(1)
  await page.getByLabel(labels.name,{exact:true}).fill('Second')
  await page.getByRole('button',{name:new RegExp(labels.scope)}).click()
  await channel.getByRole('checkbox',{name:'Alpha',exact:true}).uncheck()
  await channel.getByRole('checkbox',{name:'Beta',exact:true}).check()
  if(family==='automod'){
    state.failSave=422
    await page.getByRole('button',{name:copy.common.common.save,exact:true}).click()
    await expect(page.getByRole('alert').first()).toContainText('Save 422')
    await expect(channel.getByRole('checkbox',{name:'Beta',exact:true})).toBeChecked()
  }
  await page.getByRole('button',{name:copy.common.common.save,exact:true}).click()
  await expect.poll(()=>state.posts).toBe(2)
  await expect(page.getByText('Second',{exact:true})).toBeVisible()
  expect(state.items[0]).toEqual(original)
  const stable=state.items.map(({enabled,revision,...item})=>item)
  for(const enabled of [true,false,true]){
    await page.getByRole('button',{name:words.selectVisible,exact:true}).click()
    await page.getByRole('button',{name:enabled?words.enable:words.disable,exact:true}).click()
    const dialog=page.getByRole('dialog')
    await expect(dialog).toContainText(words.stopped)
    await expect(dialog).toContainText(words.selected.replace('{{count}}','2'))
    await expect(dialog).toContainText(words.effect)
    if(enabled&&state.puts===0){
      await page.keyboard.press('Escape');await expect(dialog).toHaveCount(0)
      await expect(page.getByRole('button',{name:words.enable,exact:true})).toBeFocused()
      await page.getByRole('button',{name:words.enable,exact:true}).press('Enter')
      const audit=await new AxeBuilder({page}).analyze();expect(audit.violations.filter(item=>['critical','serious'].includes(item.impact||''))).toEqual([])
      await page.screenshot({path:testInfo.outputPath(`bulk-${family}-${locale}.png`)})
    }
    await dialog.getByRole('button',{name:words.confirm,exact:true}).click()
    await expect(dialog).toHaveCount(0)
    expect(state.items.every(item=>item.enabled===enabled)).toBe(true)
    expect(state.items.map(({enabled,revision,...item})=>item)).toEqual(stable)
  }
  await page.reload();await expect(page.getByText('Second',{exact:true})).toBeVisible()
  expect(state.posts).toBe(2);expect(state.puts).toBe(3)
  expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false)
  const audit=await new AxeBuilder({page}).analyze();expect(audit.violations.filter(item=>['critical','serious'].includes(item.impact||''))).toEqual([])
  for(const element of await page.locator('main button:not([role="switch"]):visible, main a:visible, main label:has([role="switch"]):visible').all()){const box=await element.boundingBox();if(box)expect(box.height).toBeGreaterThanOrEqual(43.5)}
  await page.screenshot({path:testInfo.outputPath(`list-${family}-${locale}.png`),fullPage:true})
  if(testInfo.project.name==='desktop'){await page.setViewportSize({width:414,height:896});expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false)}
})

for(const locale of ['ja','en'] as const)test(`rule bulk conflict and failures ${locale}`,async({page})=>{
  const words=(locale==='ja'?ja:en).moderation.operations
  const state=await fixture(page,locale,'anti_spam');state.items=[1,2].map(id=>({...defaults('anti_spam'),id,revision:1,name:`Rule ${id}`}))
  await page.goto('/servers/1/moderation/anti_spam')
  await page.getByRole('button',{name:words.selectVisible,exact:true}).click()
  await page.getByRole('button',{name:words.enable,exact:true}).click()
  const dialog=page.getByRole('dialog')
  for(const status of [403,422,409]){
    state.fail=status
    await dialog.getByRole('button',{name:words.confirm,exact:true}).click()
    await expect(dialog.getByRole('alert')).toContainText(`Failure ${status}`)
    expect(state.items.every(item=>!item.enabled)).toBe(true)
    await expect(dialog).toContainText(words.selected.replace('{{count}}','2'))
  }
  await expect(dialog.getByRole('button',{name:words.confirm,exact:true})).toBeDisabled()
  await dialog.getByRole('button',{name:words.refresh,exact:true}).click()
  await expect(dialog).toHaveCount(0)
  await page.getByRole('button',{name:words.enable,exact:true}).click()
  let release!:()=>void;state.pause=new Promise<void>(resolve=>{release=resolve})
  await dialog.getByRole('button',{name:words.confirm,exact:true}).click()
  await expect(dialog.getByRole('button',{name:words.confirm,exact:true})).toBeDisabled()
  await expect(dialog.getByRole('button',{name:words.cancel,exact:true})).toBeDisabled()
  await page.keyboard.press('Escape');await expect(dialog).toBeVisible()
  await page.keyboard.press('Enter');expect(state.puts).toBe(4)
  release()
  await expect(dialog).toHaveCount(0)
  expect(state.items.every(item=>item.enabled)).toBe(true)
  expect(state.posts).toBe(0);expect(state.puts).toBe(4)
})

for(const locale of ['ja','en'] as const)test(`rule draft recovery ${locale}`,async({page})=>{
  const copy=locale==='ja'?ja:en;const words=copy.moderation.operations
  const state=await fixture(page,locale,'anti_spam')
  state.items=[{...defaults('anti_spam'),id:1,revision:3,name:'Source',conditions:{channel_policy:'only',channel_ids:['999999999999999999']}}]
  await page.goto('/servers/1/moderation/anti_spam/rules/new?copy=1')
  await page.getByLabel(copy.moderation.rule.name,{exact:true}).fill('Keep my draft')
  await page.getByRole('button',{name:new RegExp(copy.moderation.rule.scope)}).click()
  await expect(page.getByRole('checkbox',{name:/999999999999999999/})).toBeChecked()
  await page.getByRole('button',{name:new RegExp(copy.moderation.rule.basics)}).click()
  state.templateFail=true
  page.once('dialog',dialog=>dialog.accept())
  await page.getByRole('button',{name:words.applyTemplate,exact:true}).click()
  await expect(page.getByRole('alert')).toContainText('Template unavailable')
  await expect(page.getByLabel(copy.moderation.rule.name,{exact:true})).toHaveValue('Keep my draft')
  expect(state.posts).toBe(0)
  state.templateFail=false
  await page.getByLabel(words.template,{exact:true}).selectOption('duplicate')
  page.once('dialog',dialog=>dialog.accept())
  await page.getByRole('button',{name:words.applyTemplate,exact:true}).click()
  await expect(page.getByLabel(copy.moderation.rule.name,{exact:true})).toHaveValue('')
  await expect(page.getByLabel(copy.moderation.rule.trigger,{exact:true})).toHaveValue('duplicate')
  await expect(page.getByLabel(words.similarity_percent,{exact:true})).toHaveValue('100')
  await page.getByLabel(copy.moderation.rule.name,{exact:true}).fill('Changed template')
  page.once('dialog',dialog=>dialog.dismiss())
  await page.getByRole('link',{name:words.back,exact:true}).last().click()
  await expect(page.getByLabel(copy.moderation.rule.name,{exact:true})).toHaveValue('Changed template')
  await page.getByRole('button',{name:copy.common.common.discard,exact:true}).click()
  await expect(page.getByText('Source',{exact:true})).toBeVisible()
  expect(state.posts).toBe(0);expect(state.items[0].revision).toBe(3)
})

for(const locale of ['ja','en'] as const)test(`rule execution conditions ${locale}`,async({page})=>{
  const copy=locale==='ja'?ja:en;const words=copy.moderation.operations
  const state=await fixture(page,locale,'automod');state.permissions='0';state.missing=true
  state.items=[1,2].map(id=>({...defaults('automod'),id,revision:1,name:`Rule ${id}`,conditions:{channel_policy:'only',channel_ids:['123456789012345678']},actions:[{type:'ban'}]}))
  await page.goto('/servers/1/moderation/automod')
  await page.getByRole('button',{name:words.selectVisible,exact:true}).click()
  await page.getByRole('button',{name:words.enable,exact:true}).click()
  const dialog=page.getByRole('dialog')
  await expect(dialog).toContainText(words.required)
  await expect(dialog).toContainText(words.resourceMissing)
  await expect(dialog).toContainText(copy.moderation.moderation.permissions+': Ban Members')
  await expect(dialog.getByRole('button',{name:words.confirm,exact:true})).toBeDisabled()
  await dialog.getByRole('button',{name:words.cancel,exact:true}).click()
  await page.getByRole('button',{name:words.disable,exact:true}).click()
  await dialog.getByRole('button',{name:words.confirm,exact:true}).click()
  await expect(dialog).toHaveCount(0)
  expect(state.puts).toBe(1);expect(state.posts).toBe(0)
})
