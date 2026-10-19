import { test,expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import ja from '../src/locales/ja'
import en from '../src/locales/en'
import baseline from '../src/test/fixtures/feature_metadata.json' with {type:'json'}

for(const locale of ['ja','en'] as const){
  const text=(locale==='ja'?ja:en).applications.applications
  const common=(locale==='ja'?ja:en).common.common
  test(`application creation, private review and keyboard (${locale})`,async({page},info)=>{
    let forms:Record<string,unknown>[]=[]
    let status='pending',revision=1
    const writes:Record<string,unknown>[]=[]
    const applicationFeature={id:'applications',category:'community',title:'Applications',description:'Intake',docs_path:'/docs/features/applications',fields:[],required_fields:[],required_bot_permissions:[],enabled:true,settings:{},revision:1,missing_permissions:[],maturity:'improving'}
    await page.route('**/api/v1/session',r=>r.fulfill({json:{user:{id:'99',name:'Manager',avatar_url:''},csrf_token:'test',preferences:{locale,appearance:'precision',color_scheme:'light',navigation_collapsed:false,revision:1}}}))
    await page.route('**/api/v1/guilds',r=>r.fulfill({json:{items:[{id:'1',name:'Forms test',icon:null,access:'manager'}]}}))
    await page.route('**/api/v1/guilds/1/**',r=>{
      const path=new URL(r.request().url()).pathname.split('/guilds/1/')[1]
      if(path==='features')return r.fulfill({json:{items:[...baseline.features.map(f=>({...f,title:f.id,description:'',enabled:false,settings:{},revision:1,missing_permissions:[]})),applicationFeature]}})
      if(path==='resources')return r.fulfill({json:{channels:[],roles:[],emojis:[],bot_permissions:'8'}})
      if(path==='applications/forms'){
        if(r.request().method()==='POST'){
          expect(r.request().headers()['x-csrf-token']).toBe('test')
          const value=r.request().postDataJSON();writes.push(value)
          const form={...value,id:1,guild_id:'1',revision:1,created_at:1,updated_at:1}
          forms=[form];return r.fulfill({json:form})
        }
        return r.fulfill({json:{items:forms}})
      }
      if(path==='applications/items')return r.fulfill({json:{items:[{id:1,guild_id:'1',form_id:1,author_id:'20',snapshot:forms[0],answers:{answer:'Generated application evidence'},status,revision,created_at:1,updated_at:1,expires_at:9999999999}]}})
      if(path==='applications/items/1/review'){
        const value=r.request().postDataJSON();expect(value).toEqual({status:'approved',reason:'Checked the application',revision:1});writes.push(value);status='approved';revision++
        return r.fulfill({json:{id:1,guild_id:'1',form_id:1,author_id:'20',snapshot:forms[0],answers:{answer:'Generated application evidence'},status,revision,created_at:1,updated_at:1,expires_at:9999999999}})
      }
      if(path==='applications/items/1/events')return r.fulfill({json:{items:[{id:1,actor_id:'99',event_type:'approved',reason:'Checked the application',created_at:1}]}})
      return r.fulfill({json:{items:[]}})
    })
    await page.goto('/servers/1/applications')
    await expect(page.getByRole('heading',{name:text.title,exact:true})).toBeVisible()
    const form=page.getByRole('form',{name:text.create,exact:true})
    await form.getByRole('textbox',{name:text.formTitle}).fill('Staff application')
    await form.getByRole('textbox',{name:text.label,exact:true}).fill('Why would you like to join?')
    await form.getByRole('checkbox',{name:text.accepting}).check()
    await form.getByRole('button',{name:common.save,exact:true}).click()
    await page.getByText('#1 Staff application',{exact:true}).click()
    await expect(page.getByRole('heading',{name:`${text.edit} #1`})).toBeVisible()
    await expect(form.getByRole('textbox',{name:text.formTitle})).toHaveValue('')
    const nav=page.getByRole('navigation',{name:(locale==='ja'?ja:en).common.common.featureNavigation})
    await nav.getByRole('link',{name:text.review,exact:true}).focus()
    await page.keyboard.press('Enter')
    await expect(page.getByText('Generated application evidence')).toBeVisible()
    await page.getByRole('textbox',{name:text.reason}).fill('Checked the application')
    await page.getByRole('button',{name:text.status.approved,exact:true}).click()
    await expect(page.getByRole('button',{name:text.status.approved,exact:true})).toHaveCount(0)
    await page.getByRole('button',{name:text.history}).click()
    await expect(page.getByText(/Checked the application/)).toBeVisible()
    expect(writes).toHaveLength(2)
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
    expect((await new AxeBuilder({page}).analyze()).violations).toEqual([])
    await page.screenshot({path:info.outputPath(`applications-${locale}.png`),fullPage:true})
  })
}
