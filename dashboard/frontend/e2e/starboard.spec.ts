import {test,expect} from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import en from '../src/locales/en'
import ja from '../src/locales/ja'
import baseline from '../src/test/fixtures/feature_metadata.json' with {type:'json'}

for(const locale of ['ja','en'] as const){
  test(`starboard create reconciliation, revision conflict and retained reading (${locale})`,async({page},info)=>{
    const language=locale==='ja'?ja:en,copy=language.starboard.starboard
    let enabled=true,firstCreate=true,conflict=true,requestKey='',writes=0
    let board:{id:number;guild_id:string;actor_id:string;config:Record<string,unknown>;revision:number;created_at:number;updated_at:number}|undefined
    await page.route('**/api/v1/session',r=>r.fulfill({json:{user:{id:'40',name:'Manager',avatar_url:''},csrf_token:'test',preferences:{locale,appearance:'precision',color_scheme:'light',navigation_collapsed:false,revision:1}}}))
    await page.route('**/api/v1/guilds',r=>r.fulfill({json:{items:[{id:'1',name:'Highlights test',icon:null,access:'manager'}]}}))
    await page.route('**/api/v1/guilds/1/**',r=>{
      const path=new URL(r.request().url()).pathname.split('/guilds/1/')[1]
      if(path==='features')return r.fulfill({json:{items:[...baseline.features.map(f=>({...f,enabled:true,settings:{},revision:1,missing_permissions:[]})),{id:'starboard',category:'engagement',title:copy.title,description:'',docs_path:'/docs/features/starboard',fields:[],required_fields:[],required_bot_permissions:[],enabled,settings:{},revision:1,missing_permissions:[],maturity:'improving'}]}})
      if(path==='resources')return r.fulfill({json:{channels:[{id:'10',name:'Generated source',type:0},{id:'20',name:'Generated destination',type:0}],roles:[],emojis:[],bot_permissions:'8'}})
      if(path==='starboard/boards'&&r.request().method()==='GET')return r.fulfill({json:{items:board?[board]:[]}})
      if(path==='starboard/boards'&&r.request().method()==='POST'){
        writes++;expect(r.request().headers()['x-csrf-token']).toBe('test')
        const body=r.request().postDataJSON()
        if(firstCreate){firstCreate=false;requestKey=body.request_key;board={id:1,guild_id:'1',actor_id:'40',config:body.config,revision:1,created_at:1,updated_at:1};return r.fulfill({status:503,json:{detail:{code:'upstream_unavailable',message:'Generated create response missing'}}})}
        expect(body.request_key).toBe(requestKey);expect(body.config).toEqual(board!.config)
        return r.fulfill({json:board})
      }
      if(path==='starboard/boards/1'&&r.request().method()==='PUT'){
        const body=r.request().postDataJSON();expect(body.revision).toBe(board!.revision)
        if(conflict){conflict=false;board={...board!,revision:2,config:{...board!.config,name:'Remote board'}};return r.fulfill({status:409,json:{detail:{code:'revision_conflict',message:'Generated board conflict'}}})}
        board={...board!,revision:board!.revision+1,config:body.config};return r.fulfill({json:board})
      }
      if(path.startsWith('starboard/boards/1/entries'))return r.fulfill({json:{items:[]}})
      if(path==='starboard/boards/1/history')return r.fulfill({json:{events:[],delivery:[],source_fetches:[],publications:[{id:1,entry_id:1,target_channel_id:'20',message_id:null,delivery_started:true,removed:false}]}})
      return r.fulfill({json:{items:[]}})
    })
    await page.goto('/servers/1/starboard')
    const create=page.getByRole('form',{name:copy.create,exact:true})
    await create.getByRole('textbox',{name:copy.name,exact:true}).fill('Generated board')
    await page.keyboard.press('Tab')
    await expect(create.getByRole('checkbox',{name:copy.boardEnabled,exact:true})).toBeFocused()
    await create.getByRole('checkbox',{name:copy.boardEnabled,exact:true}).check()
    await create.getByRole('combobox',{name:copy.target}).selectOption('20')
    await create.getByRole('group',{name:copy.sources,exact:true}).getByRole('checkbox',{name:'Generated source',exact:true}).check()
    await create.getByRole('button',{name:language.common.common.save,exact:true}).click()
    await expect(create.getByText('Generated create response missing')).toBeVisible()
    await create.getByRole('button',{name:language.common.common.save,exact:true}).click()
    const editor=page.getByRole('form',{name:`${copy.edit} #1`,exact:true})
    await expect(editor).toBeVisible();expect(writes).toBe(2)
    await editor.getByRole('textbox',{name:copy.name,exact:true}).fill('Updated board')
    await editor.getByRole('button',{name:language.common.common.save,exact:true}).click()
    await expect(editor.getByText('Generated board conflict')).toBeVisible()
    await editor.getByRole('button',{name:copy.refresh,exact:true}).click()
    await expect(page.getByRole('button',{name:new RegExp(`${copy.select} #1 · Remote board`)})).toBeVisible()
    await expect(editor.getByRole('textbox',{name:copy.name,exact:true})).toHaveValue('Updated board')
    await editor.getByRole('button',{name:language.common.common.discard,exact:true}).click()
    await expect(editor.getByRole('textbox',{name:copy.name,exact:true})).toHaveValue('Remote board')
    await editor.getByRole('textbox',{name:copy.name,exact:true}).fill('N'.repeat(80))
    await editor.getByRole('button',{name:language.common.common.save,exact:true}).click()
    await expect(editor.getByRole('status')).toHaveText(language.common.editing.saved)
    await expect(editor.getByRole('button',{name:language.common.common.save,exact:true})).toBeDisabled()
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy()
    enabled=false;await page.reload()
    await page.getByRole('button',{name:new RegExp(`${copy.select} #1`)}).click()
    await expect(page.getByText(copy.disabled)).toBeVisible()
    await expect(editor.getByRole('textbox',{name:copy.name,exact:true})).toBeDisabled()
    await expect(page.getByText(copy.uncertain)).toBeVisible()
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy()
    expect((await new AxeBuilder({page}).analyze()).violations).toEqual([])
    await page.screenshot({path:info.outputPath(`starboard-${locale}.png`),fullPage:true})
  })
}
