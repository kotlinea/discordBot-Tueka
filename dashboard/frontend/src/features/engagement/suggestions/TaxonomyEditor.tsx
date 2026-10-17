import {useTranslation} from 'react-i18next'
import s from '../../../styles/App.module.css'

export function TaxonomyEditor({kind,value,onChange}:{kind:'categories'|'tags';value:string[];onChange:(value:string[])=>void}){
  const {t}=useTranslation('suggestions');const max=kind==='categories'?20:50
  return <fieldset><legend>{t(`suggestions.${kind}`)}</legend>
    {value.map((name,index)=><div className={s.rowActions} key={index}><label className={s.field}>{t('suggestions.taxonomyName',{n:index+1})}<input required maxLength={40} value={name} onChange={e=>onChange(value.map((v,i)=>i===index?e.target.value:v))}/></label><button type="button" onClick={()=>onChange(value.filter((_,i)=>i!==index))}>{t('suggestions.removeField')} {index+1}</button></div>)}
    <button type="button" disabled={value.length>=max} onClick={()=>onChange([...value,''])}>{t('suggestions.addTaxonomy')}</button>
  </fieldset>
}
