import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { I18nextProvider } from 'react-i18next'
import { createInstance } from 'i18next'
import en from '../locales/en'
import ja from '../locales/ja'
import { FormEditor } from '../features/community/applications/Forms'
import { ReviewItem } from '../features/community/applications/Review'
import { request } from '../api'
import type { ApplicationForm, ApplicationItem } from '../generated/api'

vi.mock('../api',async original=>({...await original<typeof import('../api')>(),request:vi.fn()}))
const call=vi.mocked(request)
const form:ApplicationForm={id:1,guild_id:'1',revision:2,created_at:1,updated_at:1,title:'Staff',description:'',enabled:true,fields:[{key:'why',label:'Why?',required:true,min_length:1,max_length:100,style:'paragraph'}],required_role_ids:[],denied_role_ids:[],account_age_days:0,member_age_days:0,cooldown_seconds:3600,retention_days:30}
const item:ApplicationItem={id:7,guild_id:'1',form_id:1,author_id:'20',snapshot:form,answers:{why:'Answer snapshot'},status:'pending',revision:3,created_at:1,updated_at:1,expires_at:9999999999}
async function mount(element:React.ReactNode,locale='en'){
  const i18n=createInstance();await i18n.init({lng:locale,resources:{en,ja},interpolation:{escapeValue:false}})
  const client=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}})
  const view=render(<I18nextProvider i18n={i18n}><QueryClientProvider client={client}><MemoryRouter>{element}</MemoryRouter></QueryClientProvider></I18nextProvider>)
  return {client,...view}
}
beforeEach(()=>{call.mockReset()})
afterEach(()=>cleanup())

describe('Applications',()=>{
  it.each(['ja','en'])('preserves a conflicting form draft and revision in %s',async locale=>{
    const text=(locale==='ja'?ja:en).applications.applications
    call.mockRejectedValue(new Error('revision_conflict'))
    await mount(<FormEditor guildId="1" item={form}/>,locale)
    const input=screen.getByRole('textbox',{name:text.formTitle})
    fireEvent.change(input,{target:{value:'Edited locally'}})
    fireEvent.click(screen.getByRole('button',{name:(locale==='ja'?ja:en).common.common.save}))
    expect(await screen.findByRole('alert')).toHaveTextContent('revision_conflict')
    expect(input).toHaveValue('Edited locally')
    expect(JSON.parse(String(call.mock.calls[0][2]?.body))).toMatchObject({revision:2,title:'Edited locally'})
    fireEvent.click(screen.getByRole('button',{name:(locale==='ja'?ja:en).common.common.discard}))
    expect(input).toHaveValue('Staff')
  })
  it('sends all policy and optional question fields without losing values',async()=>{
    call.mockResolvedValue(form)
    await mount(<FormEditor guildId="1" item={form} roles={[{id:'100',name:'Blocked A'},{id:'200',name:'Blocked B'}]}/>)
    const denied=within(screen.getByRole('group',{name:'Denied roles'}))
    fireEvent.click(denied.getByRole('checkbox',{name:'Blocked A'}))
    fireEvent.click(denied.getByRole('checkbox',{name:'Blocked B'}))
    fireEvent.change(screen.getByRole('spinbutton',{name:'Answer and history retention (days)'}),{target:{value:'7'}})
    fireEvent.click(screen.getByRole('button',{name:'Save changes'}))
    await waitFor(()=>expect(call).toHaveBeenCalledTimes(1))
    expect(JSON.parse(String(call.mock.calls[0][2]?.body))).toMatchObject({denied_role_ids:['100','200'],retention_days:7,fields:form.fields})
  })
  it('keeps review reason on failure and disables review while intake is off',async()=>{
    call.mockRejectedValue(new Error('conflict'))
    await mount(<ReviewItem guildId="1" item={item} enabled/>)
    const reason=screen.getByRole('textbox',{name:'Review reason'})
    expect(screen.getByRole('button',{name:'Approved'})).toBeDisabled()
    fireEvent.change(reason,{target:{value:'Evidence checked'}})
    fireEvent.click(screen.getByRole('button',{name:'Approved'}))
    expect(await screen.findByRole('alert')).toHaveTextContent('conflict')
    expect(reason).toHaveValue('Evidence checked')
    expect(JSON.parse(String(call.mock.calls[0][2]?.body))).toMatchObject({revision:3,status:'approved',reason:'Evidence checked'})
    cleanup()
    await mount(<ReviewItem guildId="1" item={item} enabled={false}/>)
    expect(screen.getByRole('textbox',{name:'Review reason'})).toBeDisabled()
    expect(screen.getByRole('button',{name:'Approved'})).toBeDisabled()
  })
  it('shows immutable question snapshot and final review history without a mutation button',async()=>{
    call.mockResolvedValue({items:[{id:1,actor_id:'99',event_type:'approved',reason:'History evidence',created_at:1}]})
    await mount(<ReviewItem guildId="1" item={{...item,status:'approved'}} enabled/>)
    expect(screen.getByText('Answer snapshot')).toBeVisible()
    expect(screen.queryByRole('button',{name:'Approved'})).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button',{name:'Review history'}))
    expect(await screen.findByText(/History evidence/)).toBeVisible()
  })
})
