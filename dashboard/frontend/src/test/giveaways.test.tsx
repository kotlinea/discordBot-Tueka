import {afterEach,describe,expect,it,vi} from 'vitest'
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react'
import {QueryClient,QueryClientProvider} from '@tanstack/react-query'
import {MemoryRouter} from 'react-router-dom'
import {I18nextProvider} from 'react-i18next'
import {createInstance} from 'i18next'
import en from '../locales/en'
import ja from '../locales/ja'
import {Editor} from '../features/engagement/giveaways/Editor'
import {History} from '../features/engagement/giveaways/History'
import {request} from '../api'
import type {GiveawayItem} from '../types'
vi.mock('../api',async original=>({...await original<typeof import('../api')>(),request:vi.fn()}))
const call=vi.mocked(request)
const item:GiveawayItem={id:1,guild_id:'1',actor_id:'20',config:{kind:'giveaway',title:'Generated campaign',description:'',channel_id:'20',ends_at:2000000000,winner_count:1,capacity:10,required_role_ids:[],denied_role_ids:[],min_account_days:0,min_member_days:0,retention_days:30},status:'draft',revision:3,message_id:null,delivery_started:false,round_number:0,ends_at:2000000000,created_at:1,updated_at:1,expires_at:2001000000}
async function mount(locale:string,history=false,create=false){
  const i18n=createInstance();await i18n.init({lng:locale,resources:{en,ja},interpolation:{escapeValue:false}})
  const client=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}}),busy=vi.fn()
  const content=(campaign:GiveawayItem,enabled=true)=><I18nextProvider i18n={i18n}><QueryClientProvider client={client}><MemoryRouter>{history?<History guildId="1" item={campaign} enabled={enabled} busy={false} onBusy={busy}/>:<Editor guildId="1" item={create?undefined:campaign} enabled={enabled} channels={[{id:'20',name:'Generated target',type:0}]} roles={[]} onBusy={busy} onCreated={vi.fn()}/>}</MemoryRouter></QueryClientProvider></I18nextProvider>
  const view=render(content(item));return {busy,update:(campaign:GiveawayItem,enabled=true)=>view.rerender(content(campaign,enabled))}
}
afterEach(()=>{cleanup();call.mockReset();vi.restoreAllMocks()})
describe('Giveaways',()=>{
  it.each(['ja','en'])('retains a conflicting draft and captured revision in %s',async locale=>{
    const language=locale==='ja'?ja:en,copy=language.giveaways.giveaways
    call.mockRejectedValue(new Error('Generated conflict'))
    const view=await mount(locale)
    fireEvent.change(screen.getByRole('textbox',{name:copy.name}),{target:{value:'Local title'}})
    view.update({...item,revision:4,config:{...item.config,title:'Remote title'}})
    fireEvent.click(screen.getByRole('button',{name:language.common.common.save}))
    await screen.findByText('Generated conflict')
    const body=JSON.parse(call.mock.calls[0][2]?.body as string)
    expect(body.revision).toBe(3);expect(body.config.title).toBe('Local title')
    fireEvent.click(screen.getByRole('button',{name:language.common.common.discard}))
    expect(screen.getByRole('textbox',{name:copy.name})).toHaveValue('Remote title')
  })
  it.each(['ja','en'])('retries an uncertain creation with the same key and event winner semantics in %s',async locale=>{
    const language=locale==='ja'?ja:en,copy=language.giveaways.giveaways
    call.mockRejectedValue(new Error('Generated unknown response'))
    await mount(locale,false,true)
    fireEvent.change(screen.getByRole('textbox',{name:copy.name}),{target:{value:'Generated event'}})
    fireEvent.change(screen.getByRole('combobox',{name:copy.kind}),{target:{value:'event'}})
    fireEvent.change(screen.getByRole('combobox',{name:new RegExp(copy.channel)}),{target:{value:'20'}})
    fireEvent.click(screen.getByRole('button',{name:language.common.common.save}))
    await screen.findByText('Generated unknown response')
    fireEvent.click(screen.getByRole('button',{name:language.common.common.save}))
    await waitFor(()=>expect(call).toHaveBeenCalledTimes(2))
    const bodies=call.mock.calls.map(([, , init])=>JSON.parse(init?.body as string))
    expect(bodies[0].request_key).toBe(bodies[1].request_key)
    expect(bodies[0].config.winner_count).toBe(0)
  })
  it.each(['ja','en'])('locks published conditions and keeps reason after a failed action in %s',async locale=>{
    const language=locale==='ja'?ja:en,copy=language.giveaways.giveaways
    call.mockImplementation(async operation=>{if(operation.startsWith('GET'))return {events:[],draws:[],entries:[],delivery:[],draw_jobs:[]} as never;throw new Error('Generated reason conflict')})
    vi.spyOn(window,'confirm').mockReturnValue(true)
    const view=await mount(locale,true)
    view.update({...item,status:'closed',round_number:1})
    fireEvent.change(screen.getByRole('textbox',{name:copy.reason}),{target:{value:'Generated reroll'}})
    view.update({...item,status:'closed',round_number:1,revision:4})
    fireEvent.click(screen.getByRole('button',{name:copy.reroll}))
    await screen.findByText('Generated reason conflict')
    const write=call.mock.calls.find(([operation])=>operation.endsWith('/reroll'))!
    expect(JSON.parse(write[2]?.body as string)).toEqual({revision:3,reason:'Generated reroll'})
    expect(screen.getByRole('textbox',{name:copy.reason})).toHaveValue('Generated reroll')
    view.update({...item,status:'closed',round_number:1},false)
    fireEvent.click(screen.getByRole('button',{name:language.common.common.discard}))
    expect(screen.getByRole('textbox',{name:copy.reason})).toHaveValue('')
  })
  it.each(['ja','en'])('shows uncertain receipts without implying delivery and routes draw retries in %s',async locale=>{
    const copy=(locale==='ja'?ja:en).giveaways.giveaways
    call.mockImplementation(async operation=>operation.startsWith('GET')?{events:[],draws:[],entries:[],delivery:[],draw_jobs:[{id:9,round_number:1,status:'failed',attempts:8,last_error:'Generated member failure'}]} as never:Promise.reject(new Error('Generated retry failure')))
    const view=await mount(locale,true)
    view.update({...item,status:'closing',delivery_started:true})
    expect(await screen.findByText(copy.uncertain)).toBeVisible()
    fireEvent.click(await screen.findByRole('button',{name:`${copy.retry} #9`}))
    await screen.findByText('Generated retry failure')
    const write=call.mock.calls.find(([operation])=>operation.endsWith('/retry'))!
    expect(write[1]).toContain('?draw=true')
    expect(JSON.parse(write[2]?.body as string)).toEqual({revision:3})
  })
})
