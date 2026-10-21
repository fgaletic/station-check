import { useEffect, useState } from 'react'
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, ReferenceArea, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { api, formatDeviation, formatTime, type Greenhouse, type SeriesPoint, type VariableHealth, type VariableId } from '../api'
import { navigate } from '../App'
import { StatusDot, StatusPill } from './Status'

const UNITS: Record<VariableId, string> = { temperature: '°C', humidity: '%', radiation: 'W/m²' }
const DEV_COLOR = { ok: 'var(--ok)', warning: 'var(--warning)', alert: 'var(--alert)', unknown: 'var(--muted)' }

const dayFmt = new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/Madrid', day: 'numeric', month: 'short' })
const toMs = (ts: string) => Date.parse(ts.endsWith('Z') ? ts : ts + 'Z')

function devStatus(v: VariableHealth, d: number) {
  const t = v.thresholds!
  return Math.abs(d) >= t.alert ? 'alert' : Math.abs(d) >= t.warning ? 'warning' : 'ok'
}

function DailyDeviation({ v }: { v: VariableHealth }) {
  if (!v.daily?.length || !v.thresholds) return null
  return (
    <ResponsiveContainer width="100%" height={70}>
      <BarChart data={v.daily} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
        <YAxis hide domain={[(min: number) => Math.min(min, -v.thresholds!.alert), (max: number) => Math.max(max, v.thresholds!.alert)]} />
        <ReferenceLine y={0} stroke="var(--line-strong)" />
        <ReferenceLine y={v.thresholds.alert} stroke="var(--alert)" strokeDasharray="3 3" />
        <ReferenceLine y={-v.thresholds.alert} stroke="var(--alert)" strokeDasharray="3 3" />
        <Tooltip
          cursor={{ fill: 'var(--hover)' }}
          formatter={(d) => [`${Number(d) > 0 ? '+' : ''}${Number(d).toFixed(1)} ${v.unit}`, 'vs usual']}
          labelFormatter={(_, p) => (p?.[0] ? dayFmt.format(new Date(p[0].payload.day)) : '')}
          contentStyle={{ background: 'var(--card)', border: '1px solid var(--line)', fontSize: 12 }}
        />
        <Bar dataKey="deviation" isAnimationActive={false}>
          {v.daily.map((d) => <Cell key={d.day} fill={DEV_COLOR[devStatus(v, d.deviation)]} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

function SeriesChart({ gh, variable }: { gh: Greenhouse; variable: VariableId }) {
  const [points, setPoints] = useState<SeriesPoint[] | null>(null)

  useEffect(() => {
    let active = true
    setPoints(null)
    api.series(gh.id, variable).then((r) => active && setPoints(r.points)).catch(() => active && setPoints([]))
    return () => { active = false }
  }, [gh.id, variable, gh.source.lastSyncAt])

  if (points === null) return <div className="chart-placeholder muted">Loading chart…</div>
  if (points.length === 0) {
    const message = gh.variables.find((v) => v.variable === variable)?.message
    return <div className="chart-placeholder muted">{message ?? 'No data yet.'}</div>
  }

  const data = points.map((p) => ({ t: toMs(p.ts), farm: p.farm, ref: p.ref }))
  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -8 }}>
        <CartesianGrid stroke="var(--line)" vertical={false} />
        <ReferenceArea x1={toMs(gh.baseline.start)} x2={toMs(gh.baseline.end)} fill="var(--baseline)"
          label={{ value: 'Baseline week', position: 'insideTopLeft', fill: 'var(--muted)', fontSize: 11 }} />
        <XAxis dataKey="t" type="number" scale="time" domain={['dataMin', 'dataMax']}
          tickFormatter={(t) => dayFmt.format(new Date(t))} stroke="var(--muted)" fontSize={12} minTickGap={40} />
        <YAxis stroke="var(--muted)" fontSize={12} width={48} allowDataOverflow={variable === 'radiation'}
          domain={variable === 'radiation' ? [0, 'auto'] : ['auto', 'auto']} />
        <Tooltip
          labelFormatter={(t) => formatTime(new Date(Number(t)).toISOString())}
          formatter={(val, name) => [`${val} ${UNITS[variable]}`, name]}
          contentStyle={{ background: 'var(--card)', border: '1px solid var(--line)', fontSize: 12 }}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Line dataKey="ref" name={`Meteocat ${gh.station.name}`} stroke="var(--ref)" dot={false}
          strokeWidth={1.5} strokeDasharray="4 3" isAnimationActive={false} />
        <Line dataKey="farm" name="Your roof station" stroke="var(--accent)" dot={false}
          strokeWidth={1.75} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  )
}

export default function GreenhouseDetail({ id }: { id: number }) {
  const [gh, setGh] = useState<Greenhouse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<VariableId | null>(null)
  const [syncing, setSyncing] = useState(false)
  const [syncNote, setSyncNote] = useState<string | null>(null)

  useEffect(() => {
    api.greenhouse(id).then((g) => {
      setGh(g)
      const worst = [...g.variables].sort((a, b) =>
        ['unknown', 'ok', 'warning', 'alert'].indexOf(b.status) - ['unknown', 'ok', 'warning', 'alert'].indexOf(a.status))[0]
      setSelected(worst.variable)
    }).catch((e: Error) => setError(e.message))
  }, [id])

  async function syncNow() {
    setSyncing(true)
    setSyncNote(null)
    try {
      const r = await api.sync(id)
      setGh(r.greenhouse)
      setSyncNote(r.error ?? `${r.newReadings} new readings from Meteocat · ${r.sentToSource} measurements sent to Source`)
    } catch (e) {
      setSyncNote((e as Error).message)
    } finally {
      setSyncing(false)
    }
  }

  async function remove() {
    if (!gh || !confirm(`Remove ${gh.name}? Its stored readings are deleted; data already sent to Source stays there.`)) return
    await api.remove(id)
    navigate('/')
  }

  if (error) return <div className="banner banner-error">{error} · <a href="#/">Back</a></div>
  if (!gh || !selected) return <div className="card muted">Loading…</div>

  return (
    <>
      <a className="back" href="#/">← All greenhouses</a>
      <section className="detail-head">
        <div>
          <h1>{gh.name} <StatusPill status={gh.status} /></h1>
          <p className="muted">
            Compared with Meteocat <strong>{gh.station.name}</strong> ({gh.station.code}), {gh.station.km} km away
            {gh.scenario !== 'none' && <> · <span className="demo-tag">Demo: {gh.scenarioLabel}</span></>}
          </p>
        </div>
      </section>

      <div className="var-grid">
        {gh.variables.map((v) => (
          <button key={v.variable} className={`card var-card ${selected === v.variable ? 'selected' : ''}`}
            onClick={() => setSelected(v.variable)}>
            <div className="var-head">
              <span><StatusDot status={v.status} /> {v.label}</span>
              <span className={`var-dev dev-${v.status}`}>{formatDeviation(v)}</span>
            </div>
            <p className="var-msg">{v.message}</p>
            <DailyDeviation v={v} />
            <div className="muted tiny">Daily difference vs the baseline week · dashed line = alert level</div>
          </button>
        ))}
      </div>

      <section className="card">
        <div className="section-head">
          <h2>{gh.variables.find((v) => v.variable === selected)?.label}: your station vs Meteocat</h2>
          <span className="muted small">Last 14 days, Catalan time</span>
        </div>
        <SeriesChart gh={gh} variable={selected} />
      </section>

      <section className="card">
        <div className="section-head">
          <h2>Source connection</h2>
          <div className="actions">
            <button className="btn" onClick={syncNow} disabled={syncing}>{syncing ? 'Syncing…' : 'Sync now'}</button>
            <button className="btn btn-quiet" onClick={remove}>Remove</button>
          </div>
        </div>
        {gh.source.lastSyncError && <div className="banner banner-error">Last sync failed: {gh.source.lastSyncError}</div>}
        {syncNote && <div className="banner">{syncNote}</div>}
        <dl className="facts">
          <div><dt>Reference sensor</dt><dd><code>{gh.source.refSensorId ?? '–'}</code></dd></div>
          <div><dt>Health-check sensor</dt><dd><code>{gh.source.healthSensorId ?? '–'}</code></dd></div>
          <div><dt>Sent to Source up to</dt><dd>{formatTime(gh.source.syncedUntil)}</dd></div>
          <div><dt>Last sync</dt><dd>{formatTime(gh.source.lastSyncAt)}</dd></div>
        </dl>
        <p className="muted small">
          Meteocat readings are sent as <code>outside_*</code> measurements, and the drift results as
          <code> weather_station_*_deviation</code>, so growers see station health inside Source next to their climate data.
        </p>
      </section>
    </>
  )
}
