import { ChevronRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import s from "../../styles/App.module.css"
import { Loading, SectionHead, Failure, Status, Empty } from "../../components/Feedback"



export function TicketSimpleList({title,body,loading,error,items,action}:{title:string;body:string;loading:boolean;error:unknown;items:Array<{id:number;title:string;body:string;active:boolean;to?:string}>;action?:React.ReactNode}){if(loading)return <Loading/>;return <main className={s.page}><SectionHead title={title} description={body} actions={action}/>{error?<Failure error={error}/>:items.length?<div className={s.featureRows}>{items.map(item=>item.to?<Link key={item.id} to={item.to}><div><strong>{item.title}</strong><span>{item.body}</span></div><Status active={item.active}>{item.active?'OK':'-'}</Status><ChevronRight/></Link>:<div className={s.ruleRow} key={item.id}><div><strong>{item.title}</strong></div><span>{item.body}</span><Status active={item.active}>{item.active?'OK':'-'}</Status></div>)}</div>:<Empty title={title} body={body} action={action}/>}</main>}
