import { useEffect, useState, type FormEvent } from 'react'
import { api, type Company, type Greenhouse, type NearestStation, type Scenario } from '../api'
import { navigate } from '../App'
import { Arrow } from './Icons'
import MapView from './MapView'

export default function AddGreenhouse() {
  const [existing, setExisting] = useState<Greenhouse[]>([])
  const [companies, setCompanies] = useState<Company[]>([])
  const [scenarios, setScenarios] = useState<Scenario[]>([])
  const [picked, setPicked] = useState<{ lat: number; lon: number } | null>(null)
  const [station, setStation] = useState<NearestStation | null>(null)
  const [name, setName] = useState('')
  const [companyId, setCompanyId] = useState('')
  const [scenario, setScenario] = useState('none')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.greenhouses().then(setExisting).catch(() => {})
    api.scenarios().then(setScenarios).catch(() => {})
    api.companies()
      .then((c) => { setCompanies(c); if (c[0]) setCompanyId(c[0].id) })
      .catch((e: Error) => setError(e.message))
  }, [])

  useEffect(() => {
    if (!picked) return
    let active = true
    setStation(null)
    api.nearestStation(picked.lat, picked.lon)
      .then((s) => active && setStation(s))
      .catch((e: Error) => active && setError(e.message))
    return () => { active = false }
  }, [picked])

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!picked) return
    setBusy(true)
    setError(null)
    try {
      const gh = await api.create({ name: name.trim(), lat: picked.lat, lon: picked.lon, companyId, scenario })
      navigate(`/greenhouse/${gh.id}`)
    } catch (err) {
      setError((err as Error).message)
      setBusy(false)
    }
  }

  return (
    <>
      <a className="back" href="#/">← All greenhouses</a>
      <section className="detail-hero">
        <p className="eyebrow">New greenhouse</p>
        <h1 className="display display-sm">Where is the greenhouse?</h1>
        <p className="lede">
          Click its location on the map. The nearest Meteocat station that measures temperature, humidity and sunlight
          becomes its reference.
        </p>
      </section>

      <div className="add-grid">
        <div className="map-wrap">
          <MapView greenhouses={existing} onPick={(lat, lon) => setPicked({ lat, lon })} picked={picked} height={480} />
        </div>

        <form className="form" onSubmit={submit}>
          <div className="field">
            <span className="field-label">Reference station</span>
            <span className={`field-static ${station ? '' : 'empty'}`}>
              {!picked ? 'Click the map first' : station ? `${station.name}, ${station.km} km` : 'Finding the nearest…'}
            </span>
            {station && <span className="muted tiny">{station.comarca} · {picked!.lat.toFixed(3)}, {picked!.lon.toFixed(3)}</span>}
          </div>
          <label className="field">
            <span className="field-label">Name</span>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Cabrils tomatoes" required maxLength={80} />
          </label>
          <label className="field">
            <span className="field-label">Grower company in Source</span>
            <select value={companyId} onChange={(e) => setCompanyId(e.target.value)} required>
              {companies.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </label>
          <label className="field">
            <span className="field-label">Roof station data <span className="demo-tag">Demo</span></span>
            <select value={scenario} onChange={(e) => setScenario(e.target.value)}>
              {scenarios.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
            </select>
            <span className="muted tiny">
              In production this comes from the climate computer. Here it's simulated, optionally with a fault.
            </span>
          </label>
          {error && <div className="banner banner-error">{error}</div>}
          <div>
            <button className="btn btn-primary" disabled={!picked || !station || !companyId || busy}>
              {busy ? 'Loading 14 days of readings…' : 'Add greenhouse'}
              <span className="btn-arrow"><Arrow /></span>
            </button>
          </div>
        </form>
      </div>
    </>
  )
}
