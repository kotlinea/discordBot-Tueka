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
describe('403 access recovery retains local draft',()=>{
 it.each(['guilds','features'] as const)('retains the draft after %s permission is restored',async query=>{
  const client=new QueryClient({defaultOptions:{queries:{retry:false,staleTime:Infinity}}})
  const guilds={items:[{id:'1',name:'Synthetic Guild',icon:null,access:'admin'}]}
  client.setQueryData(['guilds'],guilds);client.setQueryData(['features','1'],{items:[]})
  const session:Session={user:{id:'user1',name:'Synthetic',avatar_url:''},csrf_token:'fake',preferences:{locale:'en',appearance:'precision',color_scheme:'light',navigation_collapsed:false,revision:1}}
  let forbidden=false
  vi.stubGlobal('fetch',vi.fn(async()=>new Response(JSON.stringify(forbidden?{detail:{code:'forbidden',message:'Access lost',errors:[]}}:query==='guilds'?guilds:{items:[]}),{status:forbidden?403:200,headers:{'content-type':'application/json'}})))
  call.mockImplementation((operation,path)=>api(path,{method:operation.split(' ')[0]}) as never)
  await mount(<Shell session={session}/>,client)
  fireEvent.change(await screen.findByLabelText('Portal draft'),{target:{value:'Unsaved permissions draft'}})
  const key=query==='guilds'?['guilds']:['features','1']
  forbidden=true
  await act(async()=>{await client.invalidateQueries({queryKey:key})})
  expect(await screen.findByRole('alert')).toHaveTextContent('Access lost')
  const retained=screen.getByLabelText('Shell draft')
  expect(retained).not.toBeVisible()
  expect(retained.closest('[inert]')).toHaveAttribute('hidden')
  expect(screen.queryByRole('textbox',{name:'Shell draft'})).not.toBeInTheDocument()
  expect(screen.queryByLabelText('Portal draft')).not.toBeInTheDocument()
  expect(document.body.style.pointerEvents).not.toBe('none')
  expect(screen.queryByRole('button',{name:'Portal submit'})).not.toBeInTheDocument()
  expect(screen.getByRole('link',{name:'Servers'})).toHaveAttribute('href','/servers')
  forbidden=false
  await act(async()=>{await client.invalidateQueries({queryKey:key})})
  expect(await screen.findByLabelText('Shell draft')).toHaveValue('Unsaved permissions draft')
  expect(screen.getByLabelText('Portal draft')).toHaveValue('Unsaved permissions draft')
  expect(screen.getByRole('button',{name:'Portal submit'})).toBeVisible()
 })
})







describe('workspace dialog access boundary',()=>{
 it.each(['controlled','uncontrolled'] as const)('pauses an open %s dialog without discarding its draft',async mode=>{
  const changed=vi.fn()
  function DraftDialog({requestedOpen}:{requestedOpen:boolean}){
   const [draft,setDraft]=useState('Initial')
   return <Dialog.Root open={mode==='controlled'?requestedOpen:undefined} defaultOpen onOpenChange={changed}><Dialog.Trigger>Open retained dialog</Dialog.Trigger><Dialog.Portal><Dialog.Overlay/><Dialog.Content aria-describedby={undefined}><Dialog.Title>Retained dialog</Dialog.Title><input aria-label="Boundary draft" value={draft} onChange={e=>setDraft(e.target.value)}/><Dialog.Close>Close retained dialog</Dialog.Close></Dialog.Content></Dialog.Portal></Dialog.Root>
  }
  const tree=(blocked:boolean,requestedOpen=true)=><Dialog.WorkspaceDialogBoundary blocked={blocked}><DraftDialog requestedOpen={requestedOpen}/></Dialog.WorkspaceDialogBoundary>
  const view=render(tree(false))
  fireEvent.change(await screen.findByLabelText('Boundary draft'),{target:{value:'Retained draft'}})
  view.rerender(tree(true))
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  await waitFor(()=>expect(document.body.style.pointerEvents).not.toBe('none'))
  expect(changed).not.toHaveBeenCalled()
  view.rerender(tree(false))
  expect(await screen.findByLabelText('Boundary draft')).toHaveValue('Retained draft')
  fireEvent.click(screen.getByRole('button',{name:'Close retained dialog'}))
  if(mode==='controlled')view.rerender(tree(false,false))
  await waitFor(()=>expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  view.rerender(tree(true,false))
  view.rerender(tree(false,false))
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
 })
 it('does not close a dialog belonging to another access boundary',async()=>{
  const dialog=(name:string)=><Dialog.Root defaultOpen><Dialog.Portal><Dialog.Content aria-describedby={undefined}><Dialog.Title>{name}</Dialog.Title></Dialog.Content></Dialog.Portal></Dialog.Root>
  render(<><Dialog.WorkspaceDialogBoundary blocked>{dialog('Blocked workspace')}</Dialog.WorkspaceDialogBoundary><Dialog.WorkspaceDialogBoundary blocked={false}>{dialog('Other workspace')}</Dialog.WorkspaceDialogBoundary></>)
  expect(screen.queryByRole('dialog',{name:'Blocked workspace'})).not.toBeInTheDocument()
  expect(await screen.findByRole('dialog',{name:'Other workspace'})).toBeVisible()
 })
 it('keeps a default-open dialog closed until access is available',async()=>{
  const content=<Dialog.Root defaultOpen><Dialog.Portal><Dialog.Overlay/><Dialog.Content aria-describedby={undefined}><Dialog.Title>Initially blocked dialog</Dialog.Title></Dialog.Content></Dialog.Portal></Dialog.Root>
  const view=render(<Dialog.WorkspaceDialogBoundary blocked>{content}</Dialog.WorkspaceDialogBoundary>)
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  view.rerender(<Dialog.WorkspaceDialogBoundary blocked={false}>{content}</Dialog.WorkspaceDialogBoundary>)
  expect(await screen.findByRole('dialog',{name:'Initially blocked dialog'})).toBeVisible()
 })
})

