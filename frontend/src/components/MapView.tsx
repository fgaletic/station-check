import { useEffect, useRef, useState } from 'react'
import { CircleMarker, MapContainer, TileLayer, Tooltip, useMap, useMapEvents } from 'react-leaflet'
import type { Greenhouse } from '../api'

const STATUS_COLOR = {
  light: { ok: '#3f7d4e', warning: '#b7791f', alert: '#b4432f', unknown: '#80867f', ring: '#f6f9f3', pick: '#c4622d' },
  dark: { ok: '#7fbf8c', warning: '#e0a54a', alert: '#e5745d', unknown: '#889187', ring: '#0f1411', pick: '#e07a43' },
}
// Standard OSM tiles, muted with a CSS filter per theme (see .map-light / .map-dark in index.css).
const TILES = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
const ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
const CATALONIA: [number, number] = [41.65, 1.65]

function useColorScheme(): 'light' | 'dark' {
  const query = '(prefers-color-scheme: dark)'
  const [dark, setDark] = useState(() => window.matchMedia(query).matches)
  useEffect(() => {
    const mq = window.matchMedia(query)
    const onChange = () => setDark(mq.matches)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])
  return dark ? 'dark' : 'light'
}

function ClickToPick({ onPick }: { onPick: (lat: number, lon: number) => void }) {
  useMapEvents({ click: (e) => onPick(e.latlng.lat, e.latlng.lng) })
  return null
}

/** Leaflet measures its container once; re-measure when the layout changes size. */
function KeepSized() {
  const map = useMap()
  useEffect(() => {
    const observer = new ResizeObserver(() => map.invalidateSize())
    observer.observe(map.getContainer())
    return () => observer.disconnect()
  }, [map])
  return null
}

/** Zoom to the greenhouses the first time they arrive. */
function FitOnce({ greenhouses }: { greenhouses: Greenhouse[] }) {
  const map = useMap()
  const done = useRef(false)
  useEffect(() => {
    if (done.current || greenhouses.length === 0) return
    const fit = () => {
      map.invalidateSize()
      if (map.getSize().x < 50) return // not laid out yet; KeepSized will retry
      done.current = true
      map.fitBounds(greenhouses.map((g) => [g.lat, g.lon] as [number, number]), { padding: [48, 48], maxZoom: 11 })
    }
    fit()
    if (done.current) return
    map.on('resize', fit)
    return () => { map.off('resize', fit) }
  }, [map, greenhouses])
  return null
}

interface Props {
  greenhouses: Greenhouse[]
  onSelect?: (id: number) => void
  onPick?: (lat: number, lon: number) => void
  picked?: { lat: number; lon: number } | null
  height?: number
  fit?: boolean
}

export default function MapView({ greenhouses, onSelect, onPick, picked, height = 420, fit }: Props) {
  const scheme = useColorScheme()
  const colors = STATUS_COLOR[scheme]
  return (
    <div className={`map map-${scheme} ${onPick ? 'map-picking' : ''}`} style={{ height }}>
      <MapContainer center={CATALONIA} zoom={8} scrollWheelZoom style={{ height: '100%' }}>
        <TileLayer attribution={ATTRIBUTION} url={TILES} />
        {greenhouses.map((g) => (
          <CircleMarker
            key={g.id}
            center={[g.lat, g.lon]}
            radius={g.status === 'alert' ? 9 : 7}
            pathOptions={{ color: colors.ring, weight: 3, fillColor: colors[g.status], fillOpacity: 1 }}
            eventHandlers={onSelect ? { click: () => onSelect(g.id) } : undefined}
          >
            <Tooltip direction="top" offset={[0, -8]}>{g.name}</Tooltip>
          </CircleMarker>
        ))}
        {picked && (
          <CircleMarker center={[picked.lat, picked.lon]} radius={10}
            pathOptions={{ color: colors.pick, weight: 2, fillColor: colors.pick, fillOpacity: 0.25 }} />
        )}
        {onPick && <ClickToPick onPick={onPick} />}
        <KeepSized />
        {fit && <FitOnce greenhouses={greenhouses} />}
      </MapContainer>
    </div>
  )
}
