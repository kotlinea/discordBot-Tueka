import {act,cleanup,fireEvent,render,screen,waitFor,within} from '@testing-library/react'
import {afterEach,describe,expect,it,vi} from 'vitest'
import Review from '../features/community/applications/Review'
import Appeals from '../features/moderation/appeals/Inbox'
import Schedules from '../features/engagement/scheduling/Schedules'
import {request} from '../api'
import type {Feature} from '../types'
import {QueryClient,QueryClientProvider} from '@tanstack/react-query'
import {MemoryRouter,Route,Routes} from 'react-router-dom'
import {I18nextProvider} from 'react-i18next'
import {createInstance} from 'i18next'
import en from '../locales/en'
vi.mock('../api',async original=>({...await original<typeof import('../api')>(),request:vi.fn()}))
const call=vi.mocked(request)
const form={id:1,guild_id:'1',revision:1,title:'Application',description:'',enabled:true,fields:[{key:'answer',label:'Answer',style:'paragraph',required:true,min_length:1,max_length:100}],required_role_ids:[],denied_role_ids:[],account_age_days:0,member_age_days:0,cooldown_seconds:0,retention_days:30,created_at:1,updated_at:1}
const features=[{id:'applications',enabled:true},{id:'appeals',enabled:true},{id:'scheduled_messages',enabled:true}] as Feature[]
afterEach(()=>{cleanup();call.mockReset();vi.restoreAllMocks();vi.unstubAllGlobals()})
async function mount(element:React.ReactNode,client=new QueryClient({defaultOptions:{queries:{retry:false,staleTime:Infinity},mutations:{retry:false}}})){
 const i18n=createInstance();await i18n.init({lng:'en',resources:{en},interpolation:{escapeValue:false}})
 render(<I18nextProvider i18n={i18n}><QueryClientProvider client={client}><MemoryRouter initialEntries={['/servers/1/test']}><Routes><Route path="/servers/:guildId/*" element={element}/></Routes></MemoryRouter></QueryClientProvider></I18nextProvider>)
 return client
}
type Consumer='review'|'appeals'|'schedules'
function rowsFor(consumer:Consumer){return Array.from({length:50},(_,index)=>{
 const id=100-index
 if(consumer==='review')return {id,guild_id:'1',form_id:1,author_id:'20',snapshot:form,answers:{answer:'Snapshot'},status:'pending',revision:1,created_at:1,updated_at:1,expires_at:9999999999}
 if(consumer==='appeals')return {id,guild_id:'1',author_id:'20',kind:'modmail',case_id:null,original_moderator_id:null,case_action:null,application_id:null,ticket_id:null,status:'open',revision:1,created_at:1,updated_at:1,expires_at:9999999999}
 return {id,guild_id:'1',actor_id:'20',payload:{kind:'message',title:`Schedule ${id}`,body:'Scheduled body',channel_id:'10',run_at:2000000000,interval_seconds:0,occurrences:1,color:0x5865f2},next_due:2000000000,remaining:1,status:'scheduled',revision:1,retention_days:30,created_at:1,updated_at:1,expires_at:4000000000}
})}

describe('local pagination protects active consumers',()=>{
 it.each(['review','appeals','schedules'] as const)('does not discard a dirty %s editor when leaving is declined',async consumer=>{
  await paginationCase(consumer,false)
 })
 it.each(['review','appeals','schedules'] as const)('does not change pages while %s save is pending',async consumer=>{
  await paginationCase(consumer,true)
 })
})
async function paginationCase(consumer:Consumer,pending:boolean){
 const rows=rowsFor(consumer);let finish:((value:never)=>void)|undefined
 call.mockImplementation(async (operation,path)=>{
  if(!operation.startsWith('GET'))return await new Promise<never>(resolve=>{finish=resolve})
  if(path.endsWith('/resources'))return {channels:[{id:'10',name:'general',type:0}],roles:[],emojis:[]} as never
  if(path.endsWith('/history'))return {delivery:[],events:[]} as never
  if(consumer==='appeals'&&path.endsWith('/100'))return {messages:[],events:[],delivery:[]} as never
  return {items:path.includes('before=')?[]:rows,next:null} as never
 })
 const confirm=vi.spyOn(window,'confirm').mockReturnValue(false)
 await mount(consumer==='review'?<Review features={features}/>:consumer==='appeals'?<Appeals features={features}/>:<Schedules features={features}/>)
 const olderName=consumer==='review'?'Older applications':consumer==='appeals'?en.appeals.appeals.older:en.scheduling.scheduling.older
 const older=await screen.findByRole('button',{name:olderName})
 if(consumer==='appeals'){fireEvent.click(screen.getByRole('button',{name:'Read conversation #100'}));await screen.findByLabelText('Reply')}
 if(consumer==='schedules'){fireEvent.click(screen.getByRole('button',{name:`${en.scheduling.scheduling.history} #100`}));await screen.findByRole('form',{name:`${en.scheduling.scheduling.edit} #100`})}
 const editor=consumer==='schedules'?within(screen.getByRole('form',{name:`${en.scheduling.scheduling.edit} #100` })):consumer==='review'?within(screen.getByRole('region',{name:'#100'})):screen
 const input=editor.getByLabelText(consumer==='review'?'Review reason':consumer==='appeals'?'Reply':'Title')
 fireEvent.change(input,{target:{value:'Unsaved evidence'}})
 if(pending){
  fireEvent.click(editor.getByRole('button',{name:consumer==='review'?'Approved':consumer==='appeals'?'Save reply and send DM':'Save schedule'}))
  await waitFor(()=>expect(finish).toBeDefined())
 }
 fireEvent.click(older)
 await act(async()=>{})
 expect(call.mock.calls.some(([,path])=>path.includes('before='))).toBe(false)
 expect(input).toBeInTheDocument()
 expect(input).toHaveValue('Unsaved evidence')
 if(pending)expect(confirm).not.toHaveBeenCalled()
 // Pending writes are deliberately left unresolved until cleanup; no production side effect is executed.
}

