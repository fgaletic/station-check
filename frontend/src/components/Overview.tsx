import { useEffect, useState } from 'react'
import { api, formatDeviation, type Greenhouse } from '../api'
import { navigate } from '../App'
import { Arrow } from './Icons'
import MapView from './MapView'
import { StatusPill } from './Status'

function headline(greenhouses: Greenhouse[] | null) {
  if (greenhouses === null) return 'Checking roof stations…'
  if (greenhouses.length === 0) return 'Add a greenhouse to check its roof station.'
  const flagged = greenhouses.filter((g) => g.status === 'alert' || g.status === 'warning').length
  if (flagged === 0) return 'Every roof station matches Meteocat.'
  if (flagged === greenhouses.length) return 'Every roof station needs a look.'
  return `${flagged} of ${greenhouses.length} roof stations need a look.`
}

export default function Overview() {
  const [greenhouses, setGreenhouses] = useState<Greenhouse[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    const load = () =>
      api.greenhouses()
        .then((g) => { if (active) { setGreenhouses(g); setError(null) } })
        .catch((e: Error) => active && setError(e.message))
    load()
    const timer = setInterval(load, 30_000)
    return () => { active = false; clearInterval(timer) }
  }, [])

  return (
    <>
      <section className="hero">
        <div>
          <p className="eyebrow">Roof station health · Catalunya</p>
          <h1 className="display">{headline(greenhouses)}</h1>
          <p className="lede">
            Each greenhouse's roof weather station is compared with the nearest official Meteocat station. When the
            usual difference between them shifts, the sensor is probably dirty, drifting or stuck.
          </p>
        </div>
        <button className="btn btn-primary" onClick={() => navigate('/new')}>
          Add greenhouse <span className="btn-arrow"><Arrow /></span>
        </button>
      </section>

      {error && <div className="banner banner-error">Couldn't load greenhouses: {error}</div>}

      <div className="overview-grid">
        <ol className="rows">
          {greenhouses?.length === 0 && <li className="row-empty">No greenhouses yet.</li>}
          {greenhouses?.map((g) => (
            <li key={g.id}>
              <button className="row" onClick={() => navigate(`/greenhouse/${g.id}`)}>
                <span>
                  <span className="row-name">{g.name}</span>
                  <span className="row-meta">vs Meteocat {g.station.name} · {g.station.km} km</span>
                </span>
                <StatusPill status={g.status} />
                <dl className="row-figs">
                  {g.variables.map((v) => (
                    <div key={v.variable}>
                      <dt>{v.label}</dt>
                      <dd className={`dev-${v.status}`}>{formatDeviation(v)}</dd>
                    </div>
                  ))}
                </dl>
              </button>
            </li>
          ))}
        </ol>
        <div className="map-frame">
          <div className="map-wrap">
            <MapView greenhouses={greenhouses ?? []} onSelect={(id) => navigate(`/greenhouse/${id}`)} height={460} fit />
          </div>
        </div>
      </div>
    </>
  )
}
