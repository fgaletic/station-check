import { useEffect, useState } from 'react'
import { api, formatDeviation, formatTime, type Greenhouse } from '../api'
import { navigate } from '../App'
import MapView from './MapView'
import { StatusDot, StatusPill } from './Status'

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

  const needsAttention = greenhouses?.filter((g) => g.status === 'alert' || g.status === 'warning').length ?? 0

  return (
    <>
      <section className="intro">
        <div>
          <h1>Your greenhouses</h1>
          <p className="muted">
            Each roof weather station is compared with the nearest official Meteocat station. When the usual
            difference between them shifts, the sensor is probably dirty, drifting or stuck.
          </p>
        </div>
        <button className="btn btn-primary" onClick={() => navigate('/new')}>Add greenhouse</button>
      </section>

      {error && <div className="banner banner-error">Couldn't load greenhouses: {error}</div>}

      {greenhouses && (
        <p className="summary-line">
          {needsAttention === 0
            ? 'All roof stations look healthy.'
            : `${needsAttention} of ${greenhouses.length} roof stations need a look.`}
        </p>
      )}

      <div className="overview-grid">
        <div className="gh-list">
          {greenhouses === null && !error && <div className="card muted">Loading…</div>}
          {greenhouses?.length === 0 && (
            <div className="card muted">No greenhouses yet. Add one to start checking its station.</div>
          )}
          {greenhouses?.map((g) => (
            <button key={g.id} className="card gh-card" onClick={() => navigate(`/greenhouse/${g.id}`)}>
              <div className="gh-card-head">
                <strong>{g.name}</strong>
                <StatusPill status={g.status} />
              </div>
              <div className="muted small">
                vs Meteocat {g.station.name} · {g.station.km} km · synced {formatTime(g.source.lastSyncAt)}
              </div>
              <div className="gh-vars">
                {g.variables.map((v) => (
                  <span key={v.variable} className="gh-var">
                    <StatusDot status={v.status} />
                    {v.label} <span className="muted">{formatDeviation(v)}</span>
                  </span>
                ))}
              </div>
            </button>
          ))}
        </div>
        <div className="card map-card">
          <MapView greenhouses={greenhouses ?? []} onSelect={(id) => navigate(`/greenhouse/${id}`)} height={480} fit />
        </div>
      </div>
    </>
  )
}
