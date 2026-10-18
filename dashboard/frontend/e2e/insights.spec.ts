import {test,expect} from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import ja from '../src/locales/ja'
import en from '../src/locales/en'
import baseline from '../src/test/fixtures/feature_metadata.json' with {type:'json'}

for(const locale of ['ja','en'] as const){
  test(`insights missing observations, UTC period, settings conflict and retained reports (${locale})`,async({page},info)=>{
    const language=locale==='ja'?ja:en,copy=language.insights.insights
    let module={enabled:false,revision:1,settings:{channel_ids:['20'],retention_days:30,track_members:true}},conflict=true
    await page.route('**/api/v1/session',r=>r.fulfill({json:{user:{id:'40',name:'Manager',avatar_url:''},csrf_token:'test',preferences:{locale,appearance:'precision',color_scheme:'light',navigation_collapsed:false,revision:1}}}))
    await page.route('**/api/v1/guilds',r=>r.fulfill({json:{items:[{id:'1',name:'Insights test',icon:null,access:'manager'}]}}))
    await page.route('**/api/v1/guilds/1/**',async r=>{
      const url=new URL(r.request().url()),path=url.pathname.split('/guilds/1/')[1]
      if(path==='features')return r.fulfill({json:{items:[...baseline.features.map(f=>({...f,enabled:true,settings:{},revision:1,missing_permissions:[]})),{id:'insights',category:'community',title:copy.title,description:'',docs_path:'/docs/features/insights',fields:[],required_fields:[],required_bot_permissions:[],...module,missing_permissions:[],maturity:'improving'}]}})
      if(path==='resources')return r.fulfill({json:{channels:[{id:'20',name:'Generated text',type:0}],roles:[],emojis:[],bot_permissions:'8'}})
      if(path==='insights/settings'&&r.request().method()==='GET')return r.fulfill({json:module})
      if(path==='insights/settings'&&r.request().method()==='PUT'){
        const body=r.request().postDataJSON();expect(body.revision).toBe(module.revision)
        if(conflict){conflict=false;module={...module,revision:2,settings:{...module.settings,retention_days:99}};return r.fulfill({status:409,json:{detail:{code:'revision_conflict',message:'Generated settings conflict'}}})}
        module={...body,revision:body.revision+1};return r.fulfill({json:module})
      }
      if(path==='insights'){
        if(url.searchParams.get('start')==='2000-01-01')return r.fulfill({status:422,json:{detail:{code:'insights_period',message:'Generated period failure'}}})
        return r.fulfill({json:{enabled:module.enabled,collecting:module.enabled,timezone:'UTC',retention_days:module.settings.retention_days,last_observed:1780000000,days:[
          {day:'2026-10-17',observed:false,messages:null,joins:null,leaves:null,voice_seconds:null,observed_seconds:null,first_observed:null,last_observed:null},
          {day:'2026-10-18',observed:true,messages:0,joins:2,leaves:1,voice_seconds:1250,observed_seconds:300,first_observed:1780000000,last_observed:1780000300},
        ]}})
      }
      return r.fulfill({json:{items:[]}})
    })
    await page.goto('/servers/1/insights')
    await expect(page.getByText(copy.off,{exact:true})).toBeVisible()
    await expect(page.getByRole('table')).toContainText(copy.unknown)
    await page.getByLabel(copy.start,{exact:true}).fill('2000-01-01')
    await page.getByRole('button',{name:copy.apply,exact:true}).click()
    await expect(page.getByText('Generated period failure')).toBeVisible()
    await expect(page.getByLabel(copy.start,{exact:true})).toHaveValue('2000-01-01')
    await page.getByLabel(copy.start,{exact:true}).fill('2026-10-17')
    await page.getByRole('button',{name:copy.apply,exact:true}).click()
    await expect(page.getByRole('table')).toBeVisible()
    await page.getByRole('link',{name:copy.settings,exact:true}).click()
    await page.getByRole('spinbutton',{name:new RegExp(copy.retention)}).fill('10')
    await page.getByLabel(copy.enabled,{exact:true}).check()
    await page.getByRole('button',{name:language.common.common.save,exact:true}).click()
    await expect(page.getByText('Generated settings conflict')).toBeVisible()
    await expect(page.getByRole('spinbutton',{name:new RegExp(copy.retention)})).toHaveValue('10')
    await page.getByRole('button',{name:copy.refresh,exact:true}).click()
    await expect(page.getByText(language.common.editing.remoteChanged,{exact:true})).toBeVisible()
    await page.getByRole('button',{name:language.common.common.discard,exact:true}).click()
    await expect(page.getByRole('spinbutton',{name:new RegExp(copy.retention)})).toHaveValue('99')
    await page.getByRole('spinbutton',{name:new RegExp(copy.retention)}).fill('10')
    await page.getByLabel(copy.enabled,{exact:true}).check()
    await page.keyboard.press('Tab')
    await page.getByRole('button',{name:language.common.common.save,exact:true}).click()
    await expect(page.getByText(language.common.editing.saved,{exact:true})).toBeVisible()
    await page.getByRole('link',{name:copy.home,exact:true}).click()
    await expect(page.getByText(copy.collecting,{exact:true})).toBeVisible()
    await page.getByRole('combobox',{name:copy.metric,exact:true}).selectOption('voice_seconds')
    await expect(page.getByRole('img',{name:`${copy.chart} · ${copy.voice_seconds}`})).toBeVisible()
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy()
    expect((await new AxeBuilder({page}).analyze()).violations).toEqual([])
    await page.screenshot({path:info.outputPath(`insights-${locale}.png`),fullPage:true})
  })
}
