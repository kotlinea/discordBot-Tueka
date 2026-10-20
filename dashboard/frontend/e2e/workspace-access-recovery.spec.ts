import {expect,test} from '@playwright/test'
import baseline from '../src/test/fixtures/feature_metadata.json' with {type:'json'}
import ja from '../src/locales/ja'
import en from '../src/locales/en'

for(const locale of ['ja','en'] as const){
  test(`permission recovery preserves a portal draft and releases its focus trap (${locale})`,async({page})=>{
    const copy=locale==='ja'?ja:en
    let denied=false,writes=0
    let settings={enabled:true,revision:1,log_channel_id:null,denial_dm:true,denial_dm_cooldown_seconds:300}
    const features=baseline.features.map(feature=>({...feature,title:feature.id,description:'',enabled:true,settings:{},revision:1,missing_permissions:[]}))
    await page.route('**/api/v1/session',route=>route.fulfill({json:{user:{id:'1',name:'Synthetic reviewer'},csrf_token:'offline',preferences:{locale,appearance:'precision',color_scheme:'light',navigation_collapsed:false,revision:1}}}))
    await page.route('**/api/v1/guilds',route=>route.fulfill({json:{items:[{id:'1',name:'Synthetic Guild',access:'manager'}]}}))
    await page.route('**/api/v1/guilds/1/**',async route=>{
      const path=new URL(route.request().url()).pathname.split('/guilds/1/')[1]
      if(path==='features'&&denied)return route.fulfill({status:403,json:{detail:{code:'forbidden',message:'Access lost',errors:[]}}})
      if(path==='reaction-roles/settings'){
        if(route.request().method()==='PUT'){
          writes++
          const body=route.request().postDataJSON()
          expect(body).toMatchObject({revision:settings.revision,denial_dm_cooldown_seconds:900})
          settings={...body,revision:settings.revision+1}
        }
        return route.fulfill({json:settings})
      }
      const data:Record<string,unknown>={features:{items:features},overview:{features,moderation:{summary:{},events:[],lockdown:null}},resources:{channels:[],roles:[],emojis:[],bot_permissions:'0'},'reaction-roles':{settings,items:[],summary:{active:0,pending:0,failed:0,scheduled:0},recoveries:[]}}
      return route.fulfill({json:data[path]??{items:[],next:null}})
    })
    await page.clock.install()
    await page.goto('/servers/1/reaction-roles/settings')
    const modal=page.getByRole('dialog',{name:copy.reactionRoles.reactionRoles.settings})
    const input=modal.getByRole('spinbutton',{name:copy.reactionRoles.reactionRoles.dmCooldown})
    await input.fill('900')
    denied=true
    await page.clock.fastForward(31_000)
    const rejected=page.waitForResponse(response=>response.url().endsWith('/guilds/1/features')&&response.status()===403)
    await page.evaluate(()=>window.dispatchEvent(new Event('offline')))
    await page.evaluate(()=>window.dispatchEvent(new Event('online')))
    await rejected
    await expect(modal).toHaveCount(0)
    await expect(page.locator('[hidden][inert]')).toHaveCount(1)
    await expect(page.getByRole('alert').filter({hasText:'Access lost'})).toBeVisible()
    expect(await page.evaluate(()=>getComputedStyle(document.body).pointerEvents)).not.toBe('none')
    const retry=page.getByRole('button',{name:copy.common.common.retry,exact:true})
    await retry.focus()
    await expect(retry).toBeFocused()
    await page.keyboard.press('Tab')
    await expect(page.getByRole('link',{name:copy.common.workspace.returnToServers,exact:true})).toBeFocused()
    expect(writes).toBe(0)
    denied=false
    await retry.focus()
    await page.keyboard.press('Enter')
    await expect(modal).toBeVisible()
    await expect(input).toHaveValue('900')
    await modal.getByRole('button',{name:copy.common.common.save,exact:true}).click()
    await expect.poll(()=>writes).toBe(1)
  })
}
