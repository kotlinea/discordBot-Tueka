import {test,expect} from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import en from '../src/locales/en'
import ja from '../src/locales/ja'
import baseline from '../src/test/fixtures/feature_metadata.json' with {type:'json'}

for(const locale of ['ja','en'] as const){
  test(`roadmap classification, merge conflict and disabled reading (${locale})`,async({page},info)=>{
    const language=locale==='ja'?ja:en,copy=language.suggestions.suggestions
    let enabled=true,conflict=true
    let item={id:1,author_id:'20',message_id:'100',status:'pending',answers:{idea:'Generated duplicate proof'},upvotes:1,downvotes:0,reviewer_id:null,created_at:1,revision:2,category:'',tags:[] as string[],merged_into:null as number|null}
    const target={...item,id:5,revision:4,answers:{idea:'Canonical proof'}}
    await page.route('**/api/v1/session',r=>r.fulfill({json:{user:{id:'20',name:'Manager',avatar_url:''},csrf_token:'test',preferences:{locale,appearance:'precision',color_scheme:'light',navigation_collapsed:false,revision:1}}}))
    await page.route('**/api/v1/guilds',r=>r.fulfill({json:{items:[{id:'1',name:'Roadmap test',icon:null,access:'manager'}]}}))
    await page.route('**/api/v1/guilds/1/**',r=>{
      const url=new URL(r.request().url()),path=url.pathname.split('/guilds/1/')[1]
      if(path==='features')return r.fulfill({json:{items:baseline.features.map(f=>({...f,enabled:true,settings:{},revision:1,missing_permissions:[]}))}})
      if(path==='resources')return r.fulfill({json:{channels:[],roles:[],emojis:[],bot_permissions:'8'}})
      if(path==='suggestions/settings')return r.fulfill({json:{enabled,revision:1,settings:{categories:['Improvement'],tags:['UI'],retention_days:30}}})
      if(path==='suggestions/items')return r.fulfill({json:{items:[item,target].filter(v=>!url.searchParams.get('category')||v.category===url.searchParams.get('category'))}})
      if(path==='suggestions/items/1')return r.fulfill({json:item})
      if(path==='suggestions/items/5')return r.fulfill({json:target})
      if(path.endsWith('/events'))return r.fulfill({json:{items:[]}})
      if(path==='suggestions/items/1/labels'){
        expect(r.request().headers()['x-csrf-token']).toBe('test')
        expect(r.request().postDataJSON()).toEqual({category:'Improvement',tags:['UI'],revision:2})
        item={...item,category:'Improvement',tags:['UI'],revision:3}
        return r.fulfill({json:item})
      }
      if(path==='suggestions/items/1/merge'){
        expect(r.request().postDataJSON()).toEqual({target_id:5,target_revision:4,revision:3,reason:'Generated merge reason'})
        if(conflict){conflict=false;return r.fulfill({status:409,json:{detail:{code:'revision_conflict',message:'Generated conflict'}}})}
        item={...item,status:'merged',merged_into:5,revision:4}
        return r.fulfill({json:item})
      }
      return r.fulfill({json:{items:[]}})
    })
    await page.goto('/servers/1/suggestions/roadmap')
    await expect(page.getByRole('heading',{name:copy.roadmap,exact:true})).toBeVisible()
    await page.getByRole('button',{name:copy.openSuggestion.replace('{{id}}','1'),exact:true}).click()
    const labels=page.getByRole('form',{name:copy.editLabels,exact:true})
    await labels.getByRole('combobox',{name:copy.category,exact:true}).selectOption('Improvement')
    await labels.getByRole('checkbox',{name:'UI',exact:true}).check()
    await expect(page.getByRole('group',{name:copy.filters,exact:true}).getByRole('combobox',{name:copy.category,exact:true})).toBeDisabled()
    await labels.getByRole('button',{name:language.common.common.save,exact:true}).click()
    const merge=page.getByRole('form',{name:copy.merge,exact:true})
    await merge.getByRole('spinbutton',{name:copy.mergeTarget,exact:true}).fill('5')
    await merge.getByRole('button',{name:copy.lookupTarget,exact:true}).click()
    await expect(merge.getByText(/Canonical proof/)).toBeVisible()
    await merge.getByRole('textbox',{name:copy.mergeReason,exact:true}).fill('Generated merge reason')
    await merge.getByRole('button',{name:copy.merge,exact:true}).click()
    await expect(merge.getByText('Generated conflict')).toBeVisible()
    await expect(merge.getByRole('textbox',{name:copy.mergeReason,exact:true})).toHaveValue('Generated merge reason')
    await merge.getByRole('button',{name:copy.merge,exact:true}).click()
    await expect(page.getByRole('button',{name:copy.openCanonical.replace('{{id}}','5'),exact:true})).toBeVisible()
    enabled=false
    await page.reload()
    await expect(page.getByText(copy.boardDisabled)).toBeVisible()
    await page.getByRole('button',{name:copy.openSuggestion.replace('{{id}}','1'),exact:true}).click()
    await expect(page.getByRole('form',{name:copy.editLabels}).getByRole('combobox',{name:copy.category,exact:true})).toBeDisabled()
    await page.keyboard.press('Tab')
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy()
    expect((await new AxeBuilder({page}).analyze()).violations).toEqual([])
    await page.screenshot({path:info.outputPath(`roadmap-${locale}.png`),fullPage:true})
  })
}
