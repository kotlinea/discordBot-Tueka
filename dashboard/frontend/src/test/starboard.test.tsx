import {afterEach,describe,expect,it,vi} from 'vitest'
import {cleanup,fireEvent,render,screen,waitFor,within} from '@testing-library/react'
import {QueryClient,QueryClientProvider} from '@tanstack/react-query'
import {MemoryRouter} from 'react-router-dom'
import {I18nextProvider} from 'react-i18next'
import {createInstance} from 'i18next'
import en from '../locales/en'
import ja from '../locales/ja'
import {BoardEditor} from '../features/engagement/starboard/BoardEditor'
import {Records} from '../features/engagement/starboard/Records'
import {request} from '../api'
import type {StarboardItem} from '../types'
vi.mock('../api',async original=>({...await original<typeof import('../api')>(),request:vi.fn()}))
const call=vi.mocked(request)
const item:StarboardItem={id:1,guild_id:'1',actor_id:'20',config:{name:'Generated board',enabled:true,target_channel_id:'20',source_channel_ids:['10'],excluded_channel_ids:[],emoji:'⭐',threshold:3,retention_days:30},revision:3,created_at:1,updated_at:1}
async function mount(locale:string,records=false,create=false){
  const i18n=createInstance();await i18n.init({lng:locale,resources:{en,ja},interpolation:{escapeValue:false}})
  const client=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}}),busy=vi.fn()
  const content=(board:StarboardItem,enabled=true)=><I18nextProvider i18n={i18n}><QueryClientProvider client={client}><MemoryRouter>{records?<Records guildId="1" board={board} enabled={enabled} busy={false} onBusy={busy}/>:<BoardEditor guildId="1" item={create?undefined:board} enabled={enabled} channels={[{id:'10',name:'Source',type:0},{id:'20',name:'Destination',type:0}]} onBusy={busy} onCreated={vi.fn()}/>}</MemoryRouter></QueryClientProvider></I18nextProvider>
  const view=render(content(item));return {busy,update:(board:StarboardItem,enabled=true)=>view.rerender(content(board,enabled))}
}
afterEach(()=>{cleanup();call.mockReset()})
describe('Starboard',()=>{
  it.each(['ja','en'])('keeps a captured revision and draft after a remote update/conflict in %s',async locale=>{
    const language=locale==='ja'?ja:en,copy=language.starboard.starboard
    call.mockRejectedValue(new Error('revision_conflict'))
    const view=await mount(locale)
    fireEvent.change(screen.getByRole('textbox',{name:copy.name}),{target:{value:'Changed locally'}})
    view.update({...item,revision:4,config:{...item.config,name:'Changed remotely'}})
    fireEvent.click(screen.getByRole('button',{name:language.common.common.save}))
    await waitFor(()=>expect(call).toHaveBeenCalledTimes(1))
    await screen.findByText('revision_conflict')
    expect(JSON.parse(call.mock.calls[0][2]?.body as string).revision).toBe(3)
    expect(screen.getByRole('textbox',{name:copy.name})).toHaveValue('Changed locally')
    view.update({...item,revision:4,config:{...item.config,name:'Changed remotely'}},false)
    expect(screen.getByRole('textbox',{name:copy.name})).toBeDisabled()
    fireEvent.click(screen.getByRole('button',{name:language.common.common.discard}))
    expect(screen.getByRole('textbox',{name:copy.name})).toHaveValue('Changed remotely')
  })
  it.each(['ja','en'])('guards an uncommitted thread ID and preserves it in a failed save in %s',async locale=>{
    const language=locale==='ja'?ja:en,copy=language.starboard.starboard
    call.mockRejectedValue(new Error('Generated source validation failure'))
    const view=await mount(locale)
    fireEvent.change(screen.getByRole('textbox',{name:copy.extraSource}),{target:{value:'123'}})
    expect(screen.getByRole('button',{name:language.common.common.save})).toBeDisabled()
    expect(view.busy).toHaveBeenLastCalledWith(true)
    fireEvent.click(screen.getByRole('button',{name:`${copy.add} · ${copy.extraSource}`}))
    fireEvent.click(screen.getByRole('button',{name:language.common.common.save}))
    await waitFor(()=>expect(call).toHaveBeenCalledTimes(1))
    await screen.findByText('Generated source validation failure')
    expect(JSON.parse(call.mock.calls[0][2]?.body as string).config.source_channel_ids).toEqual(['10','123'])
    expect(screen.getByRole('group',{name:copy.sources})).toHaveTextContent('123')
  })
  it.each(['ja','en'])('distinguishes unknown receipts and routes source retries correctly in %s',async locale=>{
    const copy=(locale==='ja'?ja:en).starboard.starboard
    call.mockImplementation(async op=>{
      if(op.endsWith('/entries'))return {items:[]} as never
      if(op.startsWith('GET'))return {events:[],delivery:[],publications:[{id:2,entry_id:1,target_channel_id:'20',message_id:null,delivery_started:true,removed:false}],source_fetches:[{id:9,channel_id:'10',message_id:'100',status:'failed',attempts:8,last_error:'Generated fetch failure',retry_actor_id:null,retry_at:null}]} as never
      throw new Error('Generated retry failure')
    })
    await mount(locale,true)
    await screen.findByText(new RegExp(copy.uncertain))
    const source=screen.getByRole('list',{name:copy.sourceJobs})
    fireEvent.click(within(source).getByRole('button',{name:`${copy.retry} #9`}))
    await waitFor(()=>expect(call.mock.calls.some(([op])=>op.includes('/source-jobs/'))).toBe(true))
    const write=call.mock.calls.find(([op])=>op.includes('/source-jobs/'))!
    expect(JSON.parse(write[2]?.body as string)).toEqual({revision:3})
    expect(await screen.findByText('Generated retry failure')).toBeVisible()
  })
  it.each(['ja','en'])('keeps a stable create key after an uncertain response in %s',async locale=>{
    const language=locale==='ja'?ja:en,copy=language.starboard.starboard
    call.mockRejectedValue(new Error('Generated unknown response'))
    await mount(locale,false,true)
    fireEvent.change(screen.getByRole('textbox',{name:copy.name}),{target:{value:'Generated board'}})
    fireEvent.change(screen.getByRole('combobox',{name:new RegExp(copy.target)}),{target:{value:'20'}})
    fireEvent.click(within(screen.getByRole('group',{name:copy.sources})).getByRole('checkbox',{name:'Source'}))
    fireEvent.click(screen.getByRole('button',{name:language.common.common.save}))
    await screen.findByText('Generated unknown response')
    fireEvent.click(screen.getByRole('button',{name:language.common.common.save}))
    await waitFor(()=>expect(call).toHaveBeenCalledTimes(2))
    const keys=call.mock.calls.map(([, , init])=>JSON.parse(init?.body as string).request_key)
    expect(keys[0]).toMatch(/^[0-9a-f-]{36}$/);expect(keys[1]).toBe(keys[0])
  })
})
