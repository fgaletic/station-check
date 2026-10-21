import type { Status } from '../api'

const LABELS: Record<Status, string> = {
  ok: 'Healthy',
  warning: 'Check soon',
  alert: 'Needs attention',
  unknown: 'Not enough data',
}

export function StatusPill({ status }: { status: Status }) {
  return <span className={`pill pill-${status}`}>{LABELS[status]}</span>
}

export function StatusDot({ status, title }: { status: Status; title?: string }) {
  return <span className={`dot dot-${status}`} title={title ?? LABELS[status]} aria-label={title ?? LABELS[status]} />
}
