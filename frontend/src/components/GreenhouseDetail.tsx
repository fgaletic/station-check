import { useEffect, useState } from 'react'
import {
  Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ReferenceArea, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { api, formatTime, type Greenhouse, type SeriesPoint, type VariableHealth, type VariableId } from '../api'
import { navigate } from '../App'
import { StatusPill } from './Status'

const UNITS: Record<VariableId, string> = { temperature: '°C', humidity: '%', radiation: 'W/m²' }
const DEV_COLOR = { ok: 'var(--line-strong)', warning: 'var(--warning)', alert: 'var(--alert)', unknown: 'var(--muted)' }
const SEVERITY = ['unknown', 'ok', 'warning', 'alert']
const TOOLTIP_STYLE = {
  background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 0, fontSize: 12, color: 'var(--ink)',
}

const dayFmt = new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/Madrid', day: 'numeric', month: 'short' })
const toMs = (ts: string) => Date.parse(ts.endsWith('Z') ? ts : ts + 'Z')

function worstVariable(gh: Greenhouse) {
  return [...gh.variables].sort((a, b) => SEVERITY.indexOf(b.status) - SEVERITY.indexOf(a.status))[0]
}

/** One plain sentence for the page headline, built from the worst finding. */
function headline(gh: Greenhouse) {
  const v = worstVariable(gh)
  if (v.status === 'alert' || v.status === 'warning') {
    if (v.stuck) return { title: `${v.label} sensor looks frozen.`, body: v.message }
    const d = v.deviation ?? 0
    const dir = d > 0 ? 'high' : 'low'
    const size = v.variable === 'radiation' ? `${Math.abs(d).toFixed(0)}%`
      : v.variable === 'humidity' ? `${Math.abs(d).toFixed(1)} points` : `${Math.abs(d).toFixed(1)} °C`
    // The headline already states the finding; keep only the advice that follows it.
    const advice = v.message?.split(/(?<=\.)\s+/).slice(1).join(' ')
    return { title: `${v.label} reads ${size} ${dir}.`, body: advice || v.message }
  }
  if (gh.variables.every((x) => x.status === 'unknown')) {
    return { title: 'Waiting for enough data.', body: 'Meteocat publishes readings every 30 minutes, about an hour late.' }
  }
  return {
    title: `Everything matches Meteocat ${gh.station.name}.`,
    body: 'Over the last 24 hours, every sensor stayed within its usual difference from the reference station.',
  }
}

function Figure({ v }: { v: VariableHealth }) {
  if (v.deviation === null) return <div className="sensor-figure dev-unknown">–</div>
  const digits = v.unit === '%' ? 0 : 1
  const shown = Number(v.deviation.toFixed(digits))
  const value = `${shown > 0 ? '+' : shown < 0 ? '−' : ''}${Math.abs(shown).toFixed(digits)}`
  return <div className={`sensor-figure dev-${v.status}`}>{value}<small>{v.unit}</small></div>
}

function devStatus(v: VariableHealth, d: number) {
  const t = v.thresholds!
  return Math.abs(d) >= t.alert ? 'alert' : Math.abs(d) >= t.warning ? 'warning' : 'ok'
}

function DailyDeviation({ v }: { v: VariableHealth }) {
  if (!v.daily?.length || !v.thresholds) return <div style={{ height: 64 }} />
  const t = v.thresholds
  return (
    <ResponsiveContainer width="100%" height={64}>
      <BarChart data={v.daily} margin={{ top: 4, right: 0, bottom: 0, left: 0 }} barCategoryGap={2}>
        <YAxis hide domain={[(min: number) => Math.min(min, -t.alert), (max: number) => Math.max(max, t.alert)]} />
        <ReferenceLine y={0} stroke="var(--line-strong)" />
        <ReferenceLine y={t.alert} stroke="var(--alert)" strokeOpacity={0.45} strokeDasharray="2 3" />
        <ReferenceLine y={-t.alert} stroke="var(--alert)" strokeOpacity={0.45} strokeDasharray="2 3" />
        <Tooltip
          cursor={{ fill: 'var(--hover)' }}
          formatter={(d) => [`${Number(d) > 0 ? '+' : ''}${Number(d).toFixed(1)} ${v.unit}`, 'vs usual']}
          labelFormatter={(_, p) => (p?.[0] ? dayFmt.format(new Date(p[0].payload.day)) : '')}
          contentStyle={TOOLTIP_STYLE}
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

  if (points === null) return <div className="chart-placeholder">Loading…</div>
  if (points.length === 0) {
    const message = gh.variables.find((v) => v.variable === variable)?.message
    return <div className="chart-placeholder">{message ?? 'No data yet.'}</div>
  }

  const data = points.map((p) => ({ t: toMs(p.ts), farm: p.farm, ref: p.ref }))
  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart data={data} margin={{ top: 8, right: 4, bottom: 0, left: -12 }}>
        <CartesianGrid stroke="var(--line)" vertical={false} />
        <ReferenceArea x1={toMs(gh.baseline.start)} x2={toMs(gh.baseline.end)} fill="var(--baseline)" fillOpacity={1} />
        <XAxis dataKey="t" type="number" scale="time" domain={['dataMin', 'dataMax']} tickLine={false}
          axisLine={{ stroke: 'var(--line-strong)' }} tickFormatter={(t) => dayFmt.format(new Date(t))}
          fontSize={12} minTickGap={48} />
        <YAxis fontSize={12} width={48} tickLine={false} axisLine={false} allowDataOverflow={variable === 'radiation'}
          domain={variable === 'radiation' ? [0, 'auto'] : ['auto', 'auto']} />
        <Tooltip
          labelFormatter={(t) => formatTime(new Date(Number(t)).toISOString())}
          formatter={(val, name) => [`${val} ${UNITS[variable]}`, name]}
          contentStyle={TOOLTIP_STYLE}
        />
        <Line dataKey="ref" name={`Meteocat ${gh.station.name}`} stroke="var(--ref)" dot={false}
          strokeWidth={1.25} strokeDasharray="4 3" isAnimationActive={false} />
        <Line dataKey="farm" name="Roof station" stroke="var(--ink)" dot={false}
          strokeWidth={1.5} isAnimationActive={false} />
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
      setSelected(worstVariable(g).variable)
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
  if (!gh || !selected) return <p className="muted">Loading…</p>

  const { title, body } = headline(gh)
  const current = gh.variables.find((v) => v.variable === selected)!

  return (
    <>
      <a className="back" href="#/">← All greenhouses</a>
      <section className="detail-hero">
        <p className="eyebrow">
          {gh.name} · vs Meteocat {gh.station.name} ({gh.station.code}), {gh.station.km} km
          {gh.scenario !== 'none' && <> · <span className="demo-tag">Demo: {gh.scenarioLabel}</span></>}
        </p>
        <h1 className="display display-sm">{title}</h1>
        <p className="lede">{body}</p>
      </section>

      <div className="sensors">
        {gh.variables.map((v) => (
          <button key={v.variable} className={`sensor ${selected === v.variable ? 'selected' : ''}`}
            onClick={() => setSelected(v.variable)} aria-pressed={selected === v.variable}
            aria-label={`${v.label}: ${v.message}`}>
            <div className="sensor-head">
              <span className="sensor-label">{v.label}</span>
              <StatusPill status={v.status} />
            </div>
            <Figure v={v} />
            <p className="sensor-msg">{v.message}</p>
            <DailyDeviation v={v} />
            <span className="muted tiny">Daily difference from the baseline week</span>
          </button>
        ))}
      </div>

      <section className="section">
        <div className="section-head">
          <h2 className="h2">{current.label}, last 14 days</h2>
          <div className="legend">
            <span><i className="swatch-line" />Roof station</span>
            <span><i className="swatch-dash" />Meteocat {gh.station.name}</span>
            <span><i className="swatch-band" />Baseline week</span>
          </div>
        </div>
        <SeriesChart gh={gh} variable={selected} />
      </section>

      <section className="section">
        <div className="section-head">
          <h2 className="h2">Source connection</h2>
          <div className="actions">
            <button className="btn btn-text" onClick={remove}>Remove greenhouse</button>
            <button className="btn" onClick={syncNow} disabled={syncing}>{syncing ? 'Syncing…' : 'Sync now'}</button>
          </div>
        </div>
        {gh.source.lastSyncError && <div className="banner banner-error">Last sync failed: {gh.source.lastSyncError}</div>}
        {syncNote && <div className="banner">{syncNote}</div>}
        <dl className="facts">
          <div><dt>Reference sensor</dt><dd><code>{gh.source.refSensorId ?? '–'}</code></dd></div>
          <div><dt>Health-check sensor</dt><dd><code>{gh.source.healthSensorId ?? '–'}</code></dd></div>
          <div><dt>Sent to Source up to</dt><dd className="num">{formatTime(gh.source.syncedUntil)}</dd></div>
          <div><dt>Last sync</dt><dd className="num">{formatTime(gh.source.lastSyncAt)}</dd></div>
        </dl>
        <p className="muted small">
          Meteocat readings go to Source as <code>outside_*</code> measurements and the drift results as{' '}
          <code>weather_station_*_deviation</code>, so station health shows up next to the grower's climate data.
        </p>
      </section>
    </>
  )
}
