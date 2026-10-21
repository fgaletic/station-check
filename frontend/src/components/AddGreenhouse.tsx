import { useEffect, useState, type FormEvent } from 'react'
import { api, type Company, type Greenhouse, type NearestStation, type Scenario } from '../api'
import { navigate } from '../App'
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
      <h1>Add a greenhouse</h1>
      <p className="muted">Click the map where the greenhouse is. We'll pick the nearest Meteocat station as its reference.</p>

      <div className="add-grid">
        <div className="card map-card">
          <MapView greenhouses={existing} onPick={(lat, lon) => setPicked({ lat, lon })} picked={picked} height={460} />
        </div>

        <form className="card form" onSubmit={submit}>
          <label>
            Location
            <span className="field-static">
              {picked ? `${picked.lat.toFixed(4)}, ${picked.lon.toFixed(4)}` : 'Click the map'}
            </span>
          </label>
          <label>
            Reference station
            <span className="field-static">
              {!picked ? '–' : station ? `${station.name} (${station.comarca}) · ${station.km} km` : 'Finding nearest…'}
            </span>
          </label>
          <label>
            Name
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Cabrils tomatoes" required maxLength={80} />
          </label>
          <label>
            Grower company in Source
            <select value={companyId} onChange={(e) => setCompanyId(e.target.value)} required>
              {companies.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </label>
          <label>
            Roof station data <span className="demo-tag">Demo</span>
            <select value={scenario} onChange={(e) => setScenario(e.target.value)}>
              {scenarios.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
            </select>
            <span className="muted tiny">
              Real roof-station data would come from the climate computer. Here it's simulated, optionally with a fault.
            </span>
          </label>
          {error && <div className="banner banner-error">{error}</div>}
          <button className="btn btn-primary" disabled={!picked || !station || !companyId || busy}>
            {busy ? 'Loading 14 days of data…' : 'Add greenhouse'}
          </button>
        </form>
      </div>
    </>
  )
}
