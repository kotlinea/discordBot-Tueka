import {createContext,useContext,useState} from 'react'
import type {ComponentProps,ReactNode} from 'react'
import * as RadixDialog from '@radix-ui/react-dialog'

export * from '@radix-ui/react-dialog'
const BlockedContext=createContext(false)

/** Pause workspace dialogs without invoking a discard callback or changing their requested open state. */
export function WorkspaceDialogBoundary({blocked,children}:{blocked:boolean;children:ReactNode}){
  return <BlockedContext.Provider value={blocked}>{children}</BlockedContext.Provider>
}

export function Root({open,defaultOpen=false,onOpenChange,...props}:ComponentProps<typeof RadixDialog.Root>){
  const blocked=useContext(BlockedContext)
  const [uncontrolledOpen,setUncontrolledOpen]=useState(defaultOpen)
  return <RadixDialog.Root {...props} open={!blocked&&(open??uncontrolledOpen)} onOpenChange={next=>{
    if(blocked)return
    if(open===undefined)setUncontrolledOpen(next)
    onOpenChange?.(next)
  }}/>
}

/** Remove portals immediately, including forced mounts and exit animations, while access is blocked. */
export function Portal(props:ComponentProps<typeof RadixDialog.Portal>){
  const blocked=useContext(BlockedContext)
  return blocked?null:<RadixDialog.Portal {...props}/>
}
