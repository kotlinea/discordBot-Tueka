import {test,expect} from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import en from '../src/locales/en'
import ja from '../src/locales/ja'
import baseline from '../src/test/fixtures/feature_metadata.json' with {type:'json'}

for(const locale of ['ja','en'] as const){
  test(`schedule edit, conflict, cancellation and keyboard (${locale})`,async({page},info)=>{
    const copy=(locale==='ja'?ja:en).scheduling.scheduling
    let item={id:1,guild_id:'1',actor_id:'20',payload:{kind:'message',title:'Generated announcement',body:'Generated test body',channel_id:'10',run_at:Math.floor(Date.now()/1000)+3600,interval_seconds:0,occurrences:1,color:0x5865F2},next_due:Math.floor(Date.now()/1000)+3600,remaining:1,status:'scheduled',revision:1,retention_days:30,created_at:1,updated_at:1,expires_at:4_000_000_000}
    let conflict=true
    const events:{id:number;post_id:number;actor_id:string;event_type:string;detail:string;created_at:number}[]=[]
    await page.route('**/api/v1/session',r=>r.fulfill({json:{user:{id:'20',name:'Manager',avatar_url:''},csrf_token:'test',preferences:{locale,appearance:'precision',color_scheme:'light',navigation_collapsed:false,revision:1}}}))
    await page.route('**/api/v1/guilds',r=>r.fulfill({json:{items:[{id:'1',name:'Scheduling test',icon:null,access:'manager'}]}}))
    await page.route('**/api/v1/guilds/1/**',r=>{
      const path=new URL(r.request().url()).pathname.split('/guilds/1/')[1]
      if(path==='features')return r.fulfill({json:{items:[...baseline.features.map(f=>({...f,enabled:true,settings:{},revision:1,missing_permissions:[]})),{id:'scheduled_messages',category:'engagement',title:copy.title,description:'',docs_path:'/docs/features/scheduled-messages',fields:['retention_days'],required_fields:[],required_bot_permissions:[],enabled:true,settings:{retention_days:30},revision:1,missing_permissions:[],maturity:'improving'}]}})
      if(path==='resources')return r.fulfill({json:{channels:[{id:'10',name:'generated-test',type:0}],roles:[],emojis:[],bot_permissions:'8'}})
      if(path==='schedules/items')return r.fulfill({json:{items:[item]}})
      if(path==='schedules/items/1/history')return r.fulfill({json:{events,delivery:[]}})
      if(path==='schedules/items/1'&&r.request().method()==='PUT'){
        expect(r.request().headers()['x-csrf-token']).toBe('test')
        const body=r.request().postDataJSON();expect(body.revision).toBe(item.revision)
        if(conflict){conflict=false;return r.fulfill({status:409,json:{detail:{code:'revision_conflict',message:'Generated conflict'}}})}
        item={...item,payload:body.payload,revision:2};events.push({id:1,post_id:1,actor_id:'20',event_type:'rescheduled',detail:'',created_at:2})
        return r.fulfill({json:item})
      }
      if(path==='schedules/items/1/cancel'){
        expect(r.request().postDataJSON().revision).toBe(2)
        item={...item,status:'cancelled',remaining:0,revision:3}
        return r.fulfill({json:item})
      }
      return r.fulfill({json:{items:[]}})
    })
    await page.goto('/servers/1/schedules')
    await expect(page.getByRole('heading',{name:copy.title,exact:true})).toBeVisible()
    await page.getByRole('button',{name:`${copy.history} #1`}).click()
    const editor=page.getByRole('form',{name:`${copy.edit} #1`})
    await editor.getByLabel(copy.name,{exact:true}).fill('Updated announcement')
    await expect(page.getByRole('button',{name:`${copy.cancel} #1`})).toBeDisabled()
    await editor.getByRole('button',{name:copy.save,exact:true}).click()
    await expect(editor.getByLabel(copy.name,{exact:true})).toHaveValue('Updated announcement')
    await expect(editor.getByText('Generated conflict')).toBeVisible()
    await editor.getByRole('button',{name:copy.save,exact:true}).click()
    await expect(page.getByRole('heading',{name:'#1 · Updated announcement'})).toBeVisible()
    await expect(page.getByRole('listitem').filter({hasText:new RegExp(copy.status.rescheduled)})).toBeVisible()
    page.once('dialog',dialog=>dialog.accept())
    await page.getByRole('button',{name:`${copy.cancel} #1`}).click()
    await expect(page.getByText(new RegExp(copy.status.cancelled))).toBeVisible()
    await page.keyboard.press('Tab')
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy()
    expect((await new AxeBuilder({page}).analyze()).violations).toEqual([])
    await page.screenshot({path:info.outputPath(`scheduling-${locale}.png`),fullPage:true})
  })
}
