import { afterEach,describe,expect,it,vi } from 'vitest'
import { cleanup,fireEvent,render,screen,waitFor } from '@testing-library/react'
import { QueryClient,QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { I18nextProvider } from 'react-i18next'
import { createInstance } from 'i18next'
import en from '../locales/en'
import ja from '../locales/ja'
import { Conversation } from '../features/moderation/appeals/Inbox'
import { request } from '../api'
import type { AppealItem } from '../generated/api'
vi.mock('../api',async original=>({...await original<typeof import('../api')>(),request:vi.fn()}))
const call=vi.mocked(request)
const item:AppealItem={id:1,guild_id:'1',author_id:'10',kind:'appeal',case_id:7,original_moderator_id:'90',case_action:'warn',application_id:null,ticket_id:null,status:'open',revision:1,created_at:1,updated_at:1,expires_at:9999999999}
async function mount(locale='en',enabled=true){
  const i18n=createInstance();await i18n.init({lng:locale,resources:{en,ja},interpolation:{escapeValue:false}})
  const client=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}})
  return render(<I18nextProvider i18n={i18n}><QueryClientProvider client={client}><MemoryRouter><Conversation guildId="1" item={item} enabled={enabled}/></MemoryRouter></QueryClientProvider></I18nextProvider>)
}
afterEach(()=>{cleanup();call.mockReset()})
const detail={messages:[{id:1,actor_id:'10',staff:false,content:'Private generated text',created_at:1}],events:[],delivery:[]}
describe('Appeals',()=>{
  it.each(['ja','en'])('keeps conflicting drafts and captured revision in %s',async locale=>{
    const copy=(locale==='ja'?ja:en).appeals.appeals
    call.mockImplementation(async op=>{if(op.startsWith('GET'))return detail as never;throw new Error('revision_conflict')})
    await mount(locale)
    fireEvent.click(screen.getByRole('button',{name:`${copy.open} #1`}))
    await screen.findByText('Private generated text')
    fireEvent.change(screen.getByLabelText(copy.message),{target:{value:'Draft reply'}})
    fireEvent.click(screen.getByRole('button',{name:copy.send}))
    await waitFor(()=>expect(call.mock.calls.some(([op])=>op.endsWith('/reply'))).toBe(true))
    expect(screen.getByLabelText(copy.message)).toHaveValue('Draft reply')
    const write=call.mock.calls.find(([op])=>op.endsWith('/reply'))
    expect(JSON.parse(write?.[2]?.body as string)).toEqual({content:'Draft reply',revision:1})
  })
  it('does not discard a separate review draft on reply',async()=>{
    call.mockResolvedValue(detail as never);await mount();fireEvent.click(screen.getByRole('button',{name:'Read conversation #1'}));await screen.findByText('Private generated text')
    fireEvent.change(screen.getByLabelText('Reply'),{target:{value:'Reply draft'}})
    fireEvent.change(screen.getByLabelText('Review reason'),{target:{value:'Review draft'}})
    expect(screen.getByRole('button',{name:'Save reply and send DM'})).toBeDisabled()
    expect(screen.getByRole('button',{name:'Accepted'})).toBeDisabled()
    fireEvent.click(screen.getByRole('button',{name:'Discard changes'}))
    expect(screen.getByLabelText('Reply')).toHaveValue('')
  })
  it('shows delivery failure but disables writes when intake is off',async()=>{
    call.mockResolvedValue({...detail,delivery:[{id:5,status:'failed',attempts:8,delivery_started:true,discord_message_id:null}]} as never)
    await mount('en',false);fireEvent.click(screen.getByRole('button',{name:'Read conversation #1'}));await screen.findByText('Private generated text')
    expect(screen.getByLabelText('Reply')).toBeDisabled()
    expect(screen.getByRole('button',{name:'Retry DM delivery #5'})).toBeDisabled()
  })
})
