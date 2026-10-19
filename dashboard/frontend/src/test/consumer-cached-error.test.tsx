import {act,cleanup,fireEvent,render,screen,within} from '@testing-library/react'
import {afterEach,describe,expect,it,vi} from 'vitest'
import Forms from '../features/community/applications/Forms'
import {ScheduleCard} from '../features/engagement/scheduling/Schedules'
import type {ScheduleItem} from '../generated/api'
import {ApiError,request} from '../api'
import {QueryClient,QueryClientProvider} from '@tanstack/react-query'
import {MemoryRouter,Route,Routes} from 'react-router-dom'
import {I18nextProvider} from 'react-i18next'
import {createInstance} from 'i18next'
import en from '../locales/en'
vi.mock('../api',async original=>({...await original<typeof import('../api')>(),request:vi.fn()}))
const call=vi.mocked(request)
const form={id:1,guild_id:'1',revision:1,title:'Application',description:'',enabled:true,fields:[{key:'answer',label:'Answer',style:'paragraph',required:true,min_length:1,max_length:100}],required_role_ids:[],denied_role_ids:[],account_age_days:0,member_age_days:0,cooldown_seconds:0,retention_days:30,created_at:1,updated_at:1}
afterEach(()=>{cleanup();call.mockReset();vi.restoreAllMocks();vi.unstubAllGlobals()})
async function mount(element:React.ReactNode,client=new QueryClient({defaultOptions:{queries:{retry:false,staleTime:Infinity},mutations:{retry:false}}})){
 const i18n=createInstance();await i18n.init({lng:'en',resources:{en},interpolation:{escapeValue:false}})
 render(<I18nextProvider i18n={i18n}><QueryClientProvider client={client}><MemoryRouter initialEntries={['/servers/1/test']}><Routes><Route path="/servers/:guildId/*" element={element}/></Routes></MemoryRouter></QueryClientProvider></I18nextProvider>)
 return client
}
describe('consumer draft retention during cached query failures',()=>{
 it('keeps an unsaved application form through a cached 503 and recovery',async()=>{
  let failed=false
  call.mockImplementation(async (_operation,path)=>{if(failed)throw new ApiError(503,'upstream_unavailable','Synthetic outage');return (path.endsWith('/resources')?{channels:[],roles:[],emojis:[]}:{items:[form],next:null}) as never})
  const client=await mount(<Forms/>)
  const editor=await screen.findByRole('form',{name:'Create a form'})
  fireEvent.change(within(editor).getByLabelText('Form title'),{target:{value:'Unsaved application'}})
  failed=true
  await act(async()=>{await client.invalidateQueries({queryKey:['applicationForms','1']})})
  expect(await screen.findByRole('alert')).toHaveTextContent('Synthetic outage')
  expect(within(editor).getByLabelText('Form title')).toBeInTheDocument()
  expect(within(editor).getByLabelText('Form title')).toHaveValue('Unsaved application')
  expect(within(editor).getByRole('button',{name:'Save changes'})).toBeDisabled()
  failed=false
  await act(async()=>{await client.invalidateQueries({queryKey:['applicationForms','1']})})
  expect(within(await screen.findByRole('form',{name:'Create a form'})).getByLabelText('Form title')).toHaveValue('Unsaved application')
 })
})
it('keeps a nested schedule editor through a cached history 503 and recovery',async()=>{
 const item:ScheduleItem={id:7,guild_id:'1',actor_id:'20',payload:{kind:'message',title:'Original schedule',body:'Announcement',channel_id:'10',run_at:2_000_000_000,interval_seconds:0,occurrences:1,color:0x5865f2},next_due:2_000_000_000,remaining:1,status:'scheduled',revision:3,retention_days:30,created_at:1,updated_at:1,expires_at:4_000_000_000}
 let failed=false
 let writes=0
 call.mockImplementation(async operation=>{
  if(!operation.startsWith('GET')){writes++;throw new Error('Unexpected write')}
  if(failed)throw new ApiError(503,'upstream_unavailable','History temporarily unavailable')
  return {delivery:[],events:[]} as never
 })
 const client=await mount(<ScheduleCard guildId="1" item={item} enabled channels={[{id:'10',name:'general',type:0}]}/>)
 fireEvent.click(screen.getByRole('button',{name:'Delivery and audit history #7'}))
 const editor=await screen.findByRole('form',{name:'Edit an unreserved schedule #7'})
 const title=within(editor).getByLabelText('Title')
 fireEvent.change(title,{target:{value:'Unsaved nested schedule'}})
 failed=true
 await act(async()=>{await client.invalidateQueries({queryKey:['scheduleHistory','1',7]})})
 expect(await screen.findByRole('alert')).toHaveTextContent('History temporarily unavailable')
 expect(title).toBeInTheDocument()
 expect(title).toHaveValue('Unsaved nested schedule')
 expect(within(editor).getByRole('button',{name:'Save schedule'})).toBeDisabled()
 expect(writes).toBe(0)
 failed=false
 await act(async()=>{await client.invalidateQueries({queryKey:['scheduleHistory','1',7]})})
 const recovered=await screen.findByRole('form',{name:'Edit an unreserved schedule #7'})
 expect(within(recovered).getByLabelText('Title')).toHaveValue('Unsaved nested schedule')
 expect(within(recovered).getByRole('button',{name:'Save schedule'})).toBeEnabled()
})

