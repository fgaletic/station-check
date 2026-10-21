import { useEffect, useState } from 'react'
import AddGreenhouse from './components/AddGreenhouse'
import GreenhouseDetail from './components/GreenhouseDetail'
import { GaugeMark } from './components/Icons'
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
          <GaugeMark />
          Station Check
        </a>
        <span className="topbar-meta">Roof weather stations, checked against Meteocat</span>
      </header>
      <main className="page">
        {route.page === 'overview' && <Overview />}
        {route.page === 'new' && <AddGreenhouse />}
        {route.page === 'greenhouse' && <GreenhouseDetail key={route.id} id={route.id} />}
      </main>
      <footer className="footer">
        Reference data: Meteocat XEMA network, via Generalitat de Catalunya open data. Results are sent to Source
        through the Source Sensor API v2.
      </footer>
    </>
  )
}
