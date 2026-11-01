import {test,expect} from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import en from '../src/locales/en'
import ja from '../src/locales/ja'

for(const locale of ['ja','en'] as const){
 test(`delegated poll builder, privacy, conflict and keyboard (${locale})`,async({page},info)=>{
  const copy=(locale==='ja'?ja:en).polls.polls
  let item={id:1,guild_id:'1',channel_id:'10',status:'open',revision:1,created_at:1,duration_seconds:600,closes_at:1793500000,config:{question:'Anonymous question',options:['A','B'],description:'',max_choices:1,mode:'anonymous',ui:'buttons',allowed_roles:[],denied_roles:[],denied_users:[],emojis:['',''],color:0x5865f2}}
  let conflict=true
  await page.route('**/api/v1/session',r=>r.fulfill({json:{user:{id:'20',name:'Poll staff',avatar_url:''},csrf_token:'test',preferences:{locale,appearance:'precision',color_scheme:'light',navigation_collapsed:false,revision:1}}}))
  await page.route('**/api/v1/guilds',r=>r.fulfill({json:{items:[{id:'1',name:'Poll test',icon:null,access:'delegated',feature_ids:['advanced_polls']}]}}))
  await page.route('**/api/v1/guilds/1/**',r=>{
   const path=new URL(r.request().url()).pathname.split('/guilds/1/')[1]
   if(path==='features'||path==='overview')throw Error('Delegated access must not read manager metadata')
   if(path==='polls/capabilities')return r.fulfill({json:{permissions:['view','manage'],enabled:true}})
   if(path==='polls/resources')return r.fulfill({json:{channels:[{id:'10',name:'polls',type:0}],roles:[],bot_permissions:'8'}})
   if(path==='polls/items')return r.fulfill({json:{items:[item]}})
   if(path==='polls/items/1'&&r.request().method()==='PUT'){
    expect(r.request().headers()['x-csrf-token']).toBe('test')
    const body=r.request().postDataJSON();expect(body.revision).toBe(item.revision)
    if(conflict){conflict=false;return r.fulfill({status:409,json:{detail:{code:'poll_conflict',message:'Test conflict'}}})}
    item={...item,config:body.config,closes_at:body.closes_at,revision:2};return r.fulfill({json:item})
   }
   return r.fulfill({json:{events:[],delivery:[]}})
  })
  await page.goto('/servers/1/modules/advanced_polls')
  await expect(page.getByRole('heading',{name:copy.title,exact:true})).toBeVisible()
  await expect(page.getByText(copy.disclosure.ballots,{exact:true})).toHaveCount(0)
  await page.getByRole('button',{name:copy.edit,exact:true}).click()
  const editor=page.getByRole('form',{name:copy.edit,exact:true})
  await editor.getByRole('textbox',{name:copy.question,exact:true}).fill('Updated question')
  await expect(editor.getByLabel(copy.deadline,{exact:true})).toBeEnabled()
  await editor.getByLabel(copy.deadline,{exact:true}).fill('2027-01-03T12:00')
  await editor.getByRole('button',{name:copy.save,exact:true}).click()
  await expect(editor.getByText('Test conflict')).toBeVisible()
  await expect(editor.getByRole('textbox',{name:copy.question,exact:true})).toHaveValue('Updated question')
  await editor.getByRole('button',{name:copy.save,exact:true}).click()
  await expect(page.getByRole('heading',{name:'#1 · Updated question'})).toBeVisible()
  await page.keyboard.press('Tab')
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy()
  expect((await new AxeBuilder({page}).analyze()).violations).toEqual([])
  await page.screenshot({path:info.outputPath(`polls-${locale}.png`),fullPage:true})
 })
}

