import {test,expect} from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import ja from '../src/locales/ja'
import en from '../src/locales/en'
import baseline from '../src/test/fixtures/feature_metadata.json' with {type:'json'}

for(const locale of ['ja','en'] as const){
  test(`giveaway draft, publication, audited reroll conflict and retained reading (${locale})`,async({page},info)=>{
    const language=locale==='ja'?ja:en,copy=language.giveaways.giveaways
    let enabled=true,createLost=true,rerollConflict=true,nonce=''
    let campaign:Record<string,any>|undefined
    const draws:Record<string,unknown>[]=[]
    await page.route('**/api/v1/session',r=>r.fulfill({json:{user:{id:'40',name:'Manager',avatar_url:''},csrf_token:'test',preferences:{locale,appearance:'precision',color_scheme:'light',navigation_collapsed:false,revision:1}}}))
    await page.route('**/api/v1/guilds',r=>r.fulfill({json:{items:[{id:'1',name:'Campaign test',icon:null,access:'manager'}]}}))
    await page.route('**/api/v1/guilds/1/**',async r=>{
      const path=new URL(r.request().url()).pathname.split('/guilds/1/')[1]
      if(path==='features')return r.fulfill({json:{items:[...baseline.features.map(f=>({...f,enabled:true,settings:{},revision:1,missing_permissions:[]})),{id:'giveaways',category:'engagement',title:copy.title,description:'',docs_path:'/docs/features/giveaways',fields:[],required_fields:[],required_bot_permissions:[],enabled,settings:{},revision:1,missing_permissions:[],maturity:'improving'}]}})
      if(path==='resources')return r.fulfill({json:{channels:[{id:'20',name:'Generated target',type:0}],roles:[],emojis:[],bot_permissions:'8'}})
      if(path==='giveaways'&&r.request().method()==='GET')return r.fulfill({json:{items:campaign?[campaign]:[]}})
      if(path==='giveaways'&&r.request().method()==='POST'){
        const body=r.request().postDataJSON()
        if(nonce)expect(body.request_key).toBe(nonce);else nonce=body.request_key
        campaign={id:1,guild_id:'1',actor_id:'40',config:body.config,status:'draft',revision:1,message_id:null,delivery_started:false,round_number:0,ends_at:body.config.ends_at,created_at:1,updated_at:1,expires_at:body.config.ends_at+86400}
        if(createLost){createLost=false;return r.fulfill({status:500,json:{detail:{code:'generated_unknown',message:'Generated missing response'}}})}
        return r.fulfill({json:campaign})
      }
      if(path==='giveaways/1'&&r.request().method()==='PUT'){
        const body=r.request().postDataJSON();expect(body.revision).toBe(campaign!.revision)
        campaign={...campaign,config:body.config,revision:campaign!.revision+1};return r.fulfill({json:campaign})
      }
      if(path==='giveaways/1/launch'){
        expect(r.request().postDataJSON().revision).toBe(campaign!.revision)
        campaign={...campaign,status:'closed',message_id:'100',delivery_started:true,round_number:1,revision:campaign!.revision+1}
        draws.push({id:1,campaign_id:1,round_number:1,actor_id:'40',reason:'deadline',candidates:['30','31'],winners:['30'],excluded_count:0,candidate_hash:'a'.repeat(64),created_at:1})
        return r.fulfill({json:campaign})
      }
      if(path==='giveaways/1/reroll'){
        const body=r.request().postDataJSON();expect(body.revision).toBe(campaign!.revision);expect(body.reason).toBe('Generated reroll proof')
        if(rerollConflict){rerollConflict=false;campaign={...campaign,revision:campaign!.revision+1};return r.fulfill({status:409,json:{detail:{code:'revision_conflict',message:'Generated reroll conflict'}}})}
        campaign={...campaign,round_number:2,revision:campaign!.revision+1}
        draws.push({id:2,campaign_id:1,round_number:2,actor_id:'40',reason:body.reason,candidates:['31'],winners:['31'],excluded_count:1,candidate_hash:'b'.repeat(64),created_at:2})
        return r.fulfill({json:campaign})
      }
      if(path==='giveaways/1/history')return r.fulfill({json:{events:[],draws,entries:[{campaign_id:1,user_id:'30',active:true,joined_at:1,updated_at:1}],delivery:[],draw_jobs:[]}})
      return r.fulfill({json:{items:[]}})
    })
    await page.goto('/servers/1/giveaways')
    const create=page.getByRole('form',{name:copy.create,exact:true})
    await create.getByRole('textbox',{name:copy.name,exact:true}).fill('Generated giveaway')
    await page.keyboard.press('Tab')
    await expect(create.getByRole('textbox',{name:copy.description,exact:true})).toBeFocused()
    await create.getByRole('combobox',{name:copy.channel}).selectOption('20')
    await create.getByRole('button',{name:language.common.common.save,exact:true}).click()
    await expect(create.getByText('Generated missing response')).toBeVisible()
    await create.getByRole('button',{name:language.common.common.save,exact:true}).click()
    const editor=page.getByRole('form',{name:`${copy.edit} #1`,exact:true})
    await expect(editor).toBeVisible()
    await editor.getByRole('textbox',{name:copy.name,exact:true}).fill('N'.repeat(120))
    await editor.getByRole('button',{name:language.common.common.save,exact:true}).click()
    await expect(editor.getByRole('status')).toHaveText(language.common.editing.saved)
    page.once('dialog',dialog=>dialog.accept())
    await page.getByRole('button',{name:copy.launch,exact:true}).click()
    await expect(editor.getByRole('textbox',{name:copy.name,exact:true})).toBeDisabled()
    await page.getByRole('textbox',{name:copy.reason,exact:true}).fill('Generated reroll proof')
    page.once('dialog',dialog=>dialog.accept())
    await page.getByRole('button',{name:copy.reroll,exact:true}).click()
    await expect(page.getByText('Generated reroll conflict')).toBeVisible()
    await expect(page.getByRole('textbox',{name:copy.reason,exact:true})).toHaveValue('Generated reroll proof')
    await page.getByRole('button',{name:copy.refresh,exact:true}).click()
    await expect(page.getByText(language.common.editing.remoteChanged,{exact:true})).toBeVisible()
    await expect(page.getByRole('textbox',{name:copy.reason,exact:true})).toHaveValue('Generated reroll proof')
    await page.getByRole('region',{name:copy.history,exact:true}).getByRole('button',{name:language.common.common.discard,exact:true}).click()
    await page.getByRole('textbox',{name:copy.reason,exact:true}).fill('Generated reroll proof')
    page.once('dialog',dialog=>dialog.accept())
    await page.getByRole('button',{name:copy.reroll,exact:true}).click()
    await expect(page.getByRole('heading',{name:`${copy.round} 2`,exact:true})).toBeVisible()
    await expect(page.getByRole('textbox',{name:copy.reason,exact:true})).toHaveValue('')
    enabled=false;await page.reload()
    await page.getByRole('button',{name:new RegExp(`${copy.select} #1`)}).click()
    await expect(page.getByText(copy.disabled)).toBeVisible()
    await expect(editor.getByRole('textbox',{name:copy.name,exact:true})).toBeDisabled()
    await expect(page.getByRole('heading',{name:`${copy.round} 2`,exact:true})).toBeVisible()
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy()
    expect((await new AxeBuilder({page}).analyze()).violations).toEqual([])
    await page.screenshot({path:info.outputPath(`giveaways-${locale}.png`),fullPage:true})
  })
}
