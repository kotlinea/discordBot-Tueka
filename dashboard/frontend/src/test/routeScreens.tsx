import { useParams } from 'react-router-dom'

/** Leaf view stub: the production registries, lazy bindings and nested routers remain real. */
export function routeScreen(name: string) {
  return function Screen(props: { family?: string; presentation?: { id: string }; definition?: { id: string } }) {
    const params = useParams()
    return <output data-testid="route">{JSON.stringify({ screen: name, ...params, family: props.family, provider: props.presentation?.id, feature: props.definition?.id })}</output>
  }
}
