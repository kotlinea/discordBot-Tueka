import { afterEach,describe,expect,it,vi } from 'vitest'
import { cleanup,fireEvent,render,screen,waitFor } from '@testing-library/react'
import { QueryClient,QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { I18nextProvider } from 'react-i18next'
import { createInstance } from 'i18next'
import en from '../locales/en'
import ja from '../locales/ja'
import Editor from '../features/engagement/polls/Editor'
import { SettingsEditor } from '../features/engagement/polls/Settings'
import { request } from '../api'
import type { PollItem } from '../generated/api'
vi.mock('../api',async original=>({...await original<typeof import('../api')>(),request:vi.fn()}))
const call=vi.mocked(request)
const item:PollItem={id:1,guild_id:'1',channel_id:'10',status:'open',revision:3,created_at:1,config:{question:'Original',options:['A','B'],mode:'anonymous'}}
async function mount(locale='en',enabled=true,settings=false,source:PollItem=item){
 const i18n=createInstance();await i18n.init({lng:locale,resources:{en,ja},interpolation:{escapeValue:false}})
 const client=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}})
 return render(<I18nextProvider i18n={i18n}><QueryClientProvider client={client}><MemoryRouter>{settings?<SettingsEditor guildId="1" source={{revision:1,settings:{retention_days:90,role_weights:{},role_permissions:{}}}} roles={[{id:'3',name:'Staff'}]} rights={['view','weights']}/>:<Editor guildId="1" item={source} enabled={enabled} channels={[]} roles={[]} onSaved={async()=>{}}/>}</MemoryRouter></QueryClientProvider></I18nextProvider>)
}
afterEach(()=>{cleanup();call.mockReset()})
describe('Advanced polls',()=>{
 it.each(['open','closed'] as const)('allows extending and clearing a published relative deadline (%s)',async status=>{
  const timed={...item,status,published_at:1,duration_seconds:600,closes_at:1793500000}
  call.mockResolvedValue({...timed,revision:4})
  await mount('en',true,false,timed)
  const deadline=screen.getByLabelText('Deadline (optional)')
  expect(deadline).not.toBeDisabled()
  fireEvent.change(deadline,{target:{value:'2027-01-03T12:00'}})
  fireEvent.click(screen.getByRole('button',{name:'Save'}))
  await waitFor(()=>expect(call).toHaveBeenCalledTimes(1))
  expect(JSON.parse(call.mock.calls[0][2]?.body as string).closes_at).toBe(Math.floor(new Date('2027-01-03T12:00').getTime()/1000))
  await waitFor(()=>expect(screen.getByRole('button',{name:'Save'})).toBeDisabled())
  fireEvent.change(deadline,{target:{value:''}})
  fireEvent.click(screen.getByRole('button',{name:'Save'}))
  await waitFor(()=>expect(call).toHaveBeenCalledTimes(2))
  expect(JSON.parse(call.mock.calls[1][2]?.body as string).closes_at).toBeNull()
  expect(JSON.parse(call.mock.calls[1][2]?.body as string).duration_seconds).toBe(600)
 })
 it.each(['draft','scheduled'] as const)('keeps relative and absolute deadlines exclusive before publication (%s)',async status=>{
  await mount('en',true,false,{...item,status,duration_seconds:600})
  expect(screen.getByLabelText('Deadline (optional)')).toBeDisabled()
 })
 it.each(['en','ja'])('keeps typed edits and the captured revision after a conflict (%s)',async locale=>{
  const copy=(locale==='ja'?ja:en).polls.polls
  call.mockRejectedValue(new Error('conflict'))
  await mount(locale)
  fireEvent.change(screen.getByLabelText(copy.question),{target:{value:'Edited'}})
  fireEvent.click(screen.getByRole('button',{name:copy.save}))
  await waitFor(()=>expect(call).toHaveBeenCalledTimes(1))
  expect(screen.getByLabelText(copy.question)).toHaveValue('Edited')
  expect(JSON.parse(call.mock.calls[0][2]?.body as string).revision).toBe(3)
 })
 it('disables edits while off',async()=>{
  await mount('en',false)
  expect(screen.getByLabelText('Question')).toBeDisabled()
  expect(screen.getByRole('button',{name:'Save'})).toBeDisabled()
 })
 it('supports a 25-option builder and forces select controls',async()=>{
  await mount()
  for(let n=2;n<25;n++)fireEvent.click(screen.getByRole('button',{name:'Add option'}))
  expect(screen.getByRole('button',{name:'Add option'})).toBeDisabled()
  expect(screen.getByLabelText('Voting controls')).toHaveValue('select')
  expect(screen.getByLabelText('Voting controls')).toBeDisabled()
  expect(screen.getByLabelText('Option 25')).toBeInTheDocument()
 })
 it('does not allow a weight delegate to assign management rights',async()=>{
  await mount('en',true,true)
  expect(screen.getByLabelText('Weight')).not.toBeDisabled()
  expect(screen.getByLabelText('Manage polls')).toBeDisabled()
  expect(screen.getByLabelText('Retention days after closing')).toBeDisabled()
 })
})
