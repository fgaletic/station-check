import { useEffect, useState } from 'react'
import AddGreenhouse from './components/AddGreenhouse'
import GreenhouseDetail from './components/GreenhouseDetail'
import Overview from './components/Overview'

type Route = { page: 'overview' } | { page: 'new' } | { page: 'greenhouse'; id: number }

function parseHash(hash: string): Route {
  const m = hash.match(/^#\/greenhouse\/(\d+)/)
  if (m) return { page: 'greenhouse', id: Number(m[1]) }
  if (hash.startsWith('#/new')) return { page: 'new' }
  return { page: 'overview' }
}

export function navigate(path: string) {
  window.location.hash = path
}

export default function App() {
  const [route, setRoute] = useState(() => parseHash(window.location.hash))

  useEffect(() => {
    const onChange = () => {
      setRoute(parseHash(window.location.hash))
      window.scrollTo(0, 0)
    }
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])

  return (
    <>
      <header className="topbar">
        <a className="brand" href="#/">
          <span className="brand-mark" aria-hidden>◎</span>
          Station Check
        </a>
        <span className="tagline">Is your greenhouse weather station telling the truth?</span>
      </header>
      <main className="page">
        {route.page === 'overview' && <Overview />}
        {route.page === 'new' && <AddGreenhouse />}
        {route.page === 'greenhouse' && <GreenhouseDetail key={route.id} id={route.id} />}
      </main>
      <footer className="footer">
        Reference data: Meteocat XEMA via Generalitat de Catalunya open data · Sends results to Source via the
        Source Sensor API v2
      </footer>
    </>
  )
}
