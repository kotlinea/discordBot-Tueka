import {afterEach,describe,expect,it,vi} from 'vitest'
import {cleanup,fireEvent,render,screen} from '@testing-library/react'
import {QueryClient,QueryClientProvider} from '@tanstack/react-query'
import {MemoryRouter,Route,Routes} from 'react-router-dom'
import {I18nextProvider} from 'react-i18next'
import {createInstance} from 'i18next'
import en from '../locales/en'
import ja from '../locales/ja'
import {request} from '../api'
import type {InsightsSettings,InsightsReport} from '../types'
import {SettingsEditor} from '../features/community/insights/Settings'
import Report from '../features/community/insights/Report'

vi.mock('../api',async original=>({...await original<typeof import('../api')>(),request:vi.fn()}))
const call=vi.mocked(request)
const source:InsightsSettings={enabled:false,revision:3,settings:{channel_ids:['20'],retention_days:30,track_members:true}}
const report:InsightsReport={enabled:false,collecting:false,timezone:'UTC',retention_days:30,last_observed:null,days:[
  {day:'2026-10-17',observed:false,messages:null,joins:null,leaves:null,voice_seconds:null,observed_seconds:null,first_observed:null,last_observed:null},
  {day:'2026-10-18',observed:true,messages:0,joins:2,leaves:1,voice_seconds:30,observed_seconds:60,first_observed:1,last_observed:61},
]}
async function mount(locale:string,settings=false){
  const i18n=createInstance();await i18n.init({lng:locale,resources:{ja,en},interpolation:{escapeValue:false}})
  const client=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}})
  const content=(value:InsightsSettings)=><I18nextProvider i18n={i18n}><QueryClientProvider client={client}><MemoryRouter initialEntries={['/servers/1/insights']}><Routes><Route path="/servers/:guildId/insights" element={settings?<SettingsEditor guildId="1" source={value} channels={[{id:'20',type:0,name:'Generated text'}]}/>:<Report/>}/></Routes></MemoryRouter></QueryClientProvider></I18nextProvider>
  const view=render(content(source));return {update:(value:InsightsSettings)=>view.rerender(content(value))}
}
afterEach(()=>{cleanup();call.mockReset();vi.restoreAllMocks()})
describe('Insights',()=>{
  it.each(['ja','en'])('keeps conflicting settings and original revision while OFF in %s',async locale=>{
    const language=locale==='ja'?ja:en,copy=language.insights.insights
    call.mockRejectedValue(new Error('Generated conflict'))
    const view=await mount(locale,true)
    fireEvent.change(screen.getByRole('spinbutton',{name:new RegExp(copy.retention)}),{target:{value:'10'}})
    view.update({...source,revision:4,settings:{...source.settings,retention_days:99}})
    fireEvent.click(screen.getByRole('button',{name:language.common.common.save}))
    await screen.findByText('Generated conflict')
    const body=JSON.parse(call.mock.calls[0][2]?.body as string)
    expect(body.revision).toBe(3);expect(body.settings.retention_days).toBe(10);expect(body.enabled).toBe(false)
    fireEvent.click(screen.getByRole('button',{name:language.common.common.discard}))
    expect(screen.getByRole('spinbutton',{name:new RegExp(copy.retention)})).toHaveValue(99)
  })
  it.each(['ja','en'])('distinguishes unobserved and zero with an accessible chart and table in %s',async locale=>{
    const copy=(locale==='ja'?ja:en).insights.insights
    call.mockResolvedValue(report)
    await mount(locale)
    await screen.findByText(copy.off)
    expect(screen.getAllByText(copy.unknown)).toHaveLength(5)
    expect(screen.getByRole('table')).toHaveTextContent('2026-10-18')
    expect(screen.getByRole('table')).toHaveTextContent('0')
    expect(screen.getByRole('img',{name:`${copy.chart} · ${copy.messages}`})).toBeInTheDocument()
    fireEvent.change(screen.getByRole('combobox',{name:copy.metric}),{target:{value:'voice_seconds'}})
    expect(screen.getByRole('img',{name:`${copy.chart} · ${copy.voice_seconds}`})).toBeInTheDocument()
  })
  it.each(['ja','en'])('retains requested UTC dates when a report fails in %s',async locale=>{
    const copy=(locale==='ja'?ja:en).insights.insights
    call.mockResolvedValueOnce(report).mockRejectedValue(new Error('Generated period failure'))
    await mount(locale)
    await screen.findByText(copy.off)
    fireEvent.change(screen.getByLabelText(copy.start),{target:{value:'2026-10-01'}})
    fireEvent.click(screen.getByRole('button',{name:copy.apply}))
    await screen.findByText('Generated period failure')
    expect(screen.getByLabelText(copy.start)).toHaveValue('2026-10-01')
    expect(screen.getByLabelText(copy.end)).toHaveValue('2026-10-18')
    expect(call.mock.calls.at(-1)?.[1]).toContain('start=2026-10-01&end=2026-10-18')
  })
})
