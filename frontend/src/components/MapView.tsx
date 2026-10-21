import { useEffect, useRef } from 'react'
import { CircleMarker, MapContainer, TileLayer, Tooltip, useMap, useMapEvents } from 'react-leaflet'
import type { Greenhouse } from '../api'

const STATUS_COLOR = { ok: '#2f9e5b', warning: '#d99a1e', alert: '#d64545', unknown: '#8a938f' }
const CATALONIA: [number, number] = [41.65, 1.65]

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
  center?: [number, number]
  zoom?: number
  fit?: boolean
}

export default function MapView({ greenhouses, onSelect, onPick, picked, height = 420, center, zoom, fit }: Props) {
  return (
    <div className={`map ${onPick ? 'map-picking' : ''}`} style={{ height }}>
      <MapContainer center={center ?? CATALONIA} zoom={zoom ?? 8} scrollWheelZoom style={{ height: '100%' }}>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {greenhouses.map((g) => (
          <CircleMarker
            key={g.id}
            center={[g.lat, g.lon]}
            radius={9}
            pathOptions={{ color: '#fff', weight: 2, fillColor: STATUS_COLOR[g.status], fillOpacity: 1 }}
            eventHandlers={onSelect ? { click: () => onSelect(g.id) } : undefined}
          >
            <Tooltip direction="top" offset={[0, -8]}>{g.name}</Tooltip>
          </CircleMarker>
        ))}
        {picked && (
          <CircleMarker center={[picked.lat, picked.lon]} radius={10}
            pathOptions={{ color: '#1d6fd6', weight: 3, fillColor: '#1d6fd6', fillOpacity: 0.35 }} />
        )}
        {onPick && <ClickToPick onPick={onPick} />}
        <KeepSized />
        {fit && <FitOnce greenhouses={greenhouses} />}
      </MapContainer>
    </div>
  )
}
