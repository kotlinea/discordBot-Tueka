import {afterEach,describe,expect,it,vi} from 'vitest'
import {cleanup,fireEvent,render,screen,waitFor,within,act} from '@testing-library/react'
import {QueryClient,QueryClientProvider} from '@tanstack/react-query'
import {MemoryRouter,Routes,Route} from 'react-router-dom'
import {I18nextProvider} from 'react-i18next'
import {createInstance} from 'i18next'
import en from '../locales/en'
import ja from '../locales/ja'
import {LabelsEditor,MergeEditor} from '../features/engagement/suggestions/RoadmapEditors'
import Roadmap from '../features/engagement/suggestions/Roadmap'
import {request} from '../api'
import type {SuggestionItem,SuggestionSettings} from '../types'
vi.mock('../api',async original=>({...await original<typeof import('../api')>(),request:vi.fn()}))
const call=vi.mocked(request)
const item:SuggestionItem={id:1,author_id:'20',message_id:null,status:'pending',answers:{idea:'Generated duplicate'},upvotes:1,downvotes:0,reviewer_id:null,created_at:1,revision:2,category:'',tags:[]}
const settings:SuggestionSettings={categories:['改善'],tags:['UI'],channel_id:'10',log_channel_id:null,review_role_ids:[],allow_voting:true,show_author:true,form_title:'Form',form_fields:[],retention_days:30}
async function mount(kind:'labels'|'merge'|'board',locale='en'){
  const i18n=createInstance();await i18n.init({lng:locale,resources:{en,ja},interpolation:{escapeValue:false}})
  const client=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}})
  const busy=vi.fn()
  render(<I18nextProvider i18n={i18n}><QueryClientProvider client={client}><MemoryRouter initialEntries={['/servers/1/suggestions/roadmap']}><Routes><Route path="/servers/:guildId/suggestions/roadmap" element={kind==='board'?<Roadmap/>:kind==='labels'?<LabelsEditor guildId="1" item={item} settings={settings} enabled onBusy={busy}/>:<MergeEditor guildId="1" item={item} enabled onBusy={busy}/>}/></Routes></MemoryRouter></QueryClientProvider></I18nextProvider>)
  return {client,busy}
}
afterEach(()=>{cleanup();call.mockReset()})
describe('Suggestion roadmap',()=>{
  it.each(['ja','en'])('keeps category drafts and captured revision on failure in %s',async locale=>{
    const copy=(locale==='ja'?ja:en).suggestions.suggestions
    call.mockRejectedValue(new Error('revision_conflict'))
    await mount('labels',locale)
    fireEvent.change(screen.getByLabelText(copy.category),{target:{value:'改善'}})
    fireEvent.click(screen.getByRole('checkbox',{name:'UI'}))
    fireEvent.click(screen.getByRole('button',{name:(locale==='ja'?ja:en).common.common.save}))
    await waitFor(()=>expect(call).toHaveBeenCalledTimes(1))
    expect(screen.getByLabelText(copy.category)).toHaveValue('改善')
    expect(JSON.parse(call.mock.calls[0][2]?.body as string)).toEqual({category:'改善',tags:['UI'],revision:2})
  })
  it.each(['ja','en'])('previews the canonical target and preserves both revisions on merge conflict in %s',async locale=>{
    const copy=(locale==='ja'?ja:en).suggestions.suggestions
    call.mockImplementation(async op=>{if(op.startsWith('GET'))return {...item,id:5,revision:4,answers:{idea:'Canonical proof'}} as never;throw new Error('revision_conflict')})
    await mount('merge',locale)
    fireEvent.change(screen.getByLabelText(copy.mergeTarget),{target:{value:'5'}})
    fireEvent.click(screen.getByRole('button',{name:copy.lookupTarget}))
    await screen.findByText(/Canonical proof/)
    fireEvent.change(screen.getByLabelText(copy.mergeReason),{target:{value:'Generated merge reason'}})
    fireEvent.click(screen.getByRole('button',{name:copy.merge}))
    await waitFor(()=>expect(call.mock.calls.some(([op])=>op.endsWith('/merge'))).toBe(true))
    expect(screen.getByLabelText(copy.mergeReason)).toHaveValue('Generated merge reason')
    const write=call.mock.calls.find(([op])=>op.endsWith('/merge'))!
    expect(JSON.parse(write[2]?.body as string)).toEqual({target_id:5,target_revision:4,revision:2,reason:'Generated merge reason'})
  })
  it('preserves a draft outside moving columns and locks other operations and filters',async()=>{
    call.mockImplementation(async op=>{
      if(op.endsWith('/suggestions/settings'))return {enabled:true,settings} as never
      if(op==='GET /api/v1/guilds/{guild_id}/suggestions/items')return {items:[item]} as never
      if(op==='GET /api/v1/guilds/{guild_id}/suggestions/items/{suggestion_id}')return item as never
      return {items:[]} as never
    })
    const {client}=await mount('board')
    fireEvent.click(await screen.findByRole('button',{name:'Open suggestion #1'}))
    const editor=await screen.findByRole('form',{name:'Edit category and tags'})
    fireEvent.change(within(editor).getByLabelText('Category'),{target:{value:'改善'}})
    expect(screen.getByRole('button',{name:'Close actions'})).toBeDisabled()
    expect(screen.getByLabelText('Canonical suggestion number')).toBeDisabled()
    expect(screen.getByRole('group',{name:'Suggestion filters'})).toBeDisabled()
    await act(async()=>{client.setQueryData(['roadmapDetail','1',1],{...item,status:'merged',revision:3,merged_into:5})})
    expect(within(editor).getByLabelText('Category')).toHaveValue('改善')
  })
  it('refreshes the selected detail after reviewing a suggestion',async()=>{
    let current={...item}
    call.mockImplementation(async op=>{
      if(op.endsWith('/suggestions/settings'))return {enabled:true,settings} as never
      if(op==='GET /api/v1/guilds/{guild_id}/suggestions/items')return {items:[current]} as never
      if(op==='GET /api/v1/guilds/{guild_id}/suggestions/items/{suggestion_id}')return current as never
      if(op.endsWith('/review')){current={...current,status:'reviewing',revision:3};return current as never}
      return {items:[]} as never
    })
    await mount('board')
    fireEvent.click(await screen.findByRole('button',{name:'Open suggestion #1'}))
    fireEvent.change(await screen.findByLabelText('Review reason'),{target:{value:'Generated review'}})
    fireEvent.click(screen.getByRole('button',{name:'In review'}))
    await screen.findByRole('heading',{name:'#1 · In review'})
  })
})
