import { test,expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import en from '../src/locales/en'
import ja from '../src/locales/ja'
import baseline from '../src/test/fixtures/feature_metadata.json' with {type:'json'}

for(const locale of ['ja','en'] as const){
  test(`private conversation review and keyboard (${locale})`,async({page},info)=>{
    const copy=(locale==='ja'?ja:en).appeals.appeals
    let item={id:1,guild_id:'1',author_id:'10',kind:'appeal',case_id:7,original_moderator_id:'90',case_action:'warn',application_id:null,ticket_id:null,status:'open',revision:1,created_at:1,updated_at:1,expires_at:9999999999}
    const messages=[{id:1,actor_id:'10',staff:false,content:'Private generated appeal',created_at:1}]
    const events:{id:number;actor_id:string;event_type:string;reason:string;created_at:number}[]=[]
    const metadata=(id:string)=>({id,category:id==='appeals'?'moderation':'community',title:id,description:'',docs_path:`/docs/features/${id}`,fields:[],required_fields:[],required_bot_permissions:[],enabled:true,settings:{},revision:1,missing_permissions:[],maturity:'improving'})
    await page.route('**/api/v1/session',r=>r.fulfill({json:{user:{id:'91',name:'Manager',avatar_url:''},csrf_token:'test',preferences:{locale,appearance:'precision',color_scheme:'light',navigation_collapsed:false,revision:1}}}))
    await page.route('**/api/v1/guilds',r=>r.fulfill({json:{items:[{id:'1',name:'Appeals test',icon:null,access:'manager'}]}}))
    await page.route('**/api/v1/guilds/1/**',r=>{
      const path=new URL(r.request().url()).pathname.split('/guilds/1/')[1]
      if(path==='features')return r.fulfill({json:{items:[...baseline.features.map(f=>({...f,...metadata(f.id),category:f.category})),metadata('applications'),metadata('appeals')]}})
      if(path==='resources')return r.fulfill({json:{channels:[],roles:[],emojis:[],bot_permissions:'8'}})
      if(path==='appeals/items')return r.fulfill({json:{items:[item]}})
      if(path==='appeals/items/1')return r.fulfill({json:{messages,events,delivery:[]}})
      if(path==='appeals/items/1/reply'){
        expect(r.request().headers()['x-csrf-token']).toBe('test')
        const body=r.request().postDataJSON();expect(body.revision).toBe(item.revision)
        messages.push({id:2,actor_id:'91',staff:true,content:body.content,created_at:2});item={...item,revision:2}
        return r.fulfill({json:item})
      }
      if(path==='appeals/items/1/review'){
        const body=r.request().postDataJSON();expect(body.revision).toBe(2)
        item={...item,status:body.status,revision:3};events.push({id:1,actor_id:'91',event_type:body.status,reason:body.reason,created_at:3})
        return r.fulfill({json:item})
      }
      return r.fulfill({json:{items:[]}})
    })
    await page.goto('/servers/1/appeals')
    await expect(page.getByRole('heading',{name:copy.title,exact:true})).toBeVisible()
    await page.getByRole('button',{name:`${copy.open} #1`}).click()
    await expect(page.getByText('Private generated appeal',{exact:true})).toBeVisible()
    await page.getByLabel(copy.message,{exact:true}).fill('Generated staff reply')
    await page.getByRole('button',{name:copy.send,exact:true}).click()
    await expect(page.getByText('Generated staff reply',{exact:true})).toBeVisible()
    await page.getByLabel(copy.reason,{exact:true}).fill('Independent review proof')
    await page.getByRole('button',{name:copy.status.accepted,exact:true}).click()
    await expect(page.getByText(/Independent review proof/)).toBeVisible()
    await expect(page.getByLabel(copy.message,{exact:true})).toHaveCount(0)
    await page.keyboard.press('Tab')
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy()
    expect((await new AxeBuilder({page}).analyze()).violations).toEqual([])
    await page.screenshot({path:info.outputPath(`appeals-${locale}.png`),fullPage:true})
  })
}
