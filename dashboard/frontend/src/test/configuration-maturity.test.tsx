import {afterEach,expect,it,vi} from 'vitest'
import {cleanup,render,screen} from '@testing-library/react'
import {QueryClient,QueryClientProvider} from '@tanstack/react-query'
import {MemoryRouter} from 'react-router-dom'
import {I18nextProvider} from 'react-i18next'
import {createInstance} from 'i18next'
import ja from '../locales/ja'
import en from '../locales/en'
import type {Feature} from '../types'
import {ConfigurationContext,ConfigurationState} from '../components/feature/ConfigurationState'

vi.mock('../api',()=>({request:vi.fn(async()=>({channels:[],roles:[]}))}))
afterEach(cleanup)
for(const locale of ['ja','en'] as const)for(const maturity of ['stable','improving','unavailable'] as const){
  it(`shows ${maturity} independently from configured OFF in ${locale}`,async()=>{
    const i18n=createInstance();await i18n.init({lng:locale,resources:{ja,en},defaultNS:'common'})
    const feature:Feature={id:'sample',category:'example',parent:null,title:'Example',description:'',docs_path:'',fields:[],required_fields:[],required_bot_permissions:[],enabled:false,settings:{},revision:1,missing_permissions:[],maturity}
    const client=new QueryClient({defaultOptions:{queries:{retry:false}}})
    render(<I18nextProvider i18n={i18n}><QueryClientProvider client={client}><MemoryRouter><ConfigurationContext.Provider value={{feature,features:[feature]}}><ConfigurationState/></ConfigurationContext.Provider></MemoryRouter></QueryClientProvider></I18nextProvider>)
    const copy=(locale==='ja'?ja:en).common
    expect(screen.getByText(`${copy.featureMaturity.label}: ${copy.featureMaturity[maturity]}`)).toBeInTheDocument()
    expect(screen.getByText(copy.editing.off)).toBeInTheDocument()
  })
}
