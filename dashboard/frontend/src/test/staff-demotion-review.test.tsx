import {useState} from 'react'
import * as Dialog from '../components/WorkspaceDialog'
import {act,cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react'
import {afterEach,describe,expect,it,vi} from 'vitest'
import {Shell} from '../app/Shell'
import {api,request} from '../api'
import type {Session} from '../types'
import {QueryClient,QueryClientProvider} from '@tanstack/react-query'
import {MemoryRouter,Route,Routes} from 'react-router-dom'
import {I18nextProvider} from 'react-i18next'
import {createInstance} from 'i18next'
import en from '../locales/en'
vi.mock('../api',async original=>({...await original<typeof import('../api')>(),request:vi.fn()}))
vi.mock('../routing/RegisteredFeatures',()=>({RegisteredFeatures:function Editor(){const [value,setValue]=useState('');return <><input aria-label="Shell draft" value={value} onChange={e=>setValue(e.target.value)}/><Dialog.Root open><Dialog.Portal><Dialog.Overlay/><Dialog.Content aria-describedby={undefined}><Dialog.Title>Synthetic portal</Dialog.Title><input aria-label="Portal draft" value={value} onChange={e=>setValue(e.target.value)}/><button>Portal submit</button></Dialog.Content></Dialog.Portal></Dialog.Root></>}}))
vi.mock('../app/Preferences',()=>({PreferencesDialog:()=>null}))
vi.mock('../app/Navigation',()=>({CommandPalette:()=>null,Breadcrumbs:()=>null}))
const call=vi.mocked(request)
afterEach(()=>{cleanup();call.mockReset();vi.restoreAllMocks();vi.unstubAllGlobals()})
async function mount(element:React.ReactNode,client=new QueryClient({defaultOptions:{queries:{retry:false,staleTime:Infinity},mutations:{retry:false}}})){
 const i18n=createInstance();await i18n.init({lng:'en',resources:{en},interpolation:{escapeValue:false}})
 render(<I18nextProvider i18n={i18n}><QueryClientProvider client={client}><MemoryRouter initialEntries={['/servers/1/test']}><Routes><Route path="/servers/:guildId/*" element={element}/></Routes></MemoryRouter></QueryClientProvider></I18nextProvider>)
 return client
}
it('allows the Ticket Staff workspace after an admin demotion with cached features 403',async()=>{
 const client=new QueryClient({defaultOptions:{queries:{retry:false,staleTime:Infinity}}})
 client.setQueryData(['guilds'],{items:[{id:'1',name:'Synthetic Guild',icon:null,access:'admin'}]})
 client.setQueryData(['features','1'],{items:[]})
 const session:Session={user:{id:'user1',name:'Synthetic',avatar_url:''},csrf_token:'fake',preferences:{locale:'en',appearance:'precision',color_scheme:'light',navigation_collapsed:false,revision:1}}
 await mount(<Shell session={session}/>,client)
 await screen.findByLabelText('Shell draft')
 await act(async()=>{await client.fetchQuery({queryKey:['features','1'],staleTime:0,queryFn:async()=>{throw new (await import('../api')).ApiError(403,'guild_forbidden','No manager access')}}).catch(()=>{})})
 await screen.findByRole('alert')
 await act(async()=>{client.setQueryData(['guilds'],{items:[{id:'1',name:'Synthetic Guild',icon:null,access:'ticket_staff'}]})})
 await waitFor(()=>expect(screen.getByLabelText('Shell draft')).toBeVisible())
})
