import * as Switch from '@radix-ui/react-switch'
import s from '../../styles/App.module.css'

export function Field({label,hint,children}:{label:string;hint?:string;children:React.ReactNode}){return <label className={s.field}><span>{label}</span>{children}{hint&&<small>{hint}</small>}</label>}

export function Toggle({label,checked,onChange,disabled=false,hint}:{label:string;checked:boolean;onChange:(value:boolean)=>void;disabled?:boolean;hint?:string}){return <label className={s.switchRow}><span><strong>{label}</strong>{hint&&<small>{hint}</small>}</span><Switch.Root checked={checked} onCheckedChange={onChange} disabled={disabled} className={s.switch}><Switch.Thumb/></Switch.Root></label>}
