import { afterEach,describe,expect,it,vi } from 'vitest'
import { cleanup,fireEvent,render,screen,waitFor } from '@testing-library/react'
import { QueryClient,QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { I18nextProvider } from 'react-i18next'
import { createInstance } from 'i18next'
import en from '../locales/en'
import ja from '../locales/ja'
import { ScheduleEditor,ScheduleCard,localTime } from '../features/engagement/scheduling/Schedules'
import { request } from '../api'
import type { ScheduleItem } from '../generated/api'
vi.mock('../api',async original=>({...await original<typeof import('../api')>(),request:vi.fn()}))
const call=vi.mocked(request)
const item:ScheduleItem={id:1,guild_id:'1',actor_id:'20',payload:{kind:'message',title:'Generated',body:'Test',channel_id:'10',run_at:2_000_000_000,interval_seconds:0,occurrences:1,color:0x5865F2},next_due:2_000_000_000,remaining:1,status:'scheduled',revision:3,retention_days:30,created_at:1,updated_at:1,expires_at:4_000_000_000}
async function mount(locale='en',enabled=true,card=false){
  const i18n=createInstance();await i18n.init({lng:locale,resources:{en,ja},interpolation:{escapeValue:false}})
  const client=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}})
  return render(<I18nextProvider i18n={i18n}><QueryClientProvider client={client}><MemoryRouter>{card?<ScheduleCard guildId="1" item={{...item,status:'completed',remaining:0}} enabled={enabled} channels={[]}/>:<ScheduleEditor guildId="1" item={item} enabled={enabled} channels={[]}/>}</MemoryRouter></QueryClientProvider></I18nextProvider>)
}
afterEach(()=>{cleanup();call.mockReset()})
describe('Scheduling',()=>{
  it.each(['ja','en'])('distinguishes reservation completion from actual delivery in %s',async locale=>{
    const copy=(locale==='ja'?ja:en).scheduling.scheduling
    call.mockResolvedValue({events:[],delivery:[{id:9,due_at:2_000_000_000,deadline:2_000_000_600,status:'completed',attempts:1,delivery_started:true,discord_receipt_id:'123'}]} as never)
    await mount(locale,true,true)
    fireEvent.click(screen.getByRole('button',{name:`${copy.history} #1`}))
    await screen.findByText(new RegExp(copy.delivered))
    expect(screen.getByText(new RegExp(copy.status.completed))).toBeInTheDocument()
  })
  it.each(['ja','en'])('preserves draft and captured revision on conflict in %s',async locale=>{
    const copy=(locale==='ja'?ja:en).scheduling.scheduling
    call.mockRejectedValue(new Error('revision_conflict'))
    await mount(locale)
    fireEvent.change(screen.getByLabelText(copy.name),{target:{value:'Edited draft'}})
    fireEvent.click(screen.getByRole('button',{name:copy.save}))
    await waitFor(()=>expect(call).toHaveBeenCalledTimes(1))
    expect(screen.getByLabelText(copy.name)).toHaveValue('Edited draft')
    expect(JSON.parse(call.mock.calls[0][2]?.body as string).revision).toBe(3)
  })
  it('disables edits and submission when the module is off',async()=>{
    await mount('en',false)
    expect(screen.getByLabelText('Title')).toBeDisabled()
    expect(screen.getByRole('button',{name:'Save schedule'})).toBeDisabled()
    expect(call).not.toHaveBeenCalled()
  })
  it('switches event mode to one occurrence and retains message draft',async()=>{
    await mount()
    fireEvent.change(screen.getByLabelText('Repeat'),{target:{value:'86400'}})
    fireEvent.change(screen.getByLabelText('Kind'),{target:{value:'event'}})
    expect(screen.queryByLabelText('Repeat')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Event start time')).toBeInTheDocument()
    expect(screen.getByLabelText('Body')).toHaveValue('Test')
    expect(localTime(2_000_000_000)).toMatch(/^\d{4}-\d\d-\d\dT\d\d:\d\d$/)
  })
})
