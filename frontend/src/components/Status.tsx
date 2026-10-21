import type { Status } from '../api'

const LABELS: Record<Status, string> = {
  ok: 'healthy',
  warning: 'check soon',
  alert: 'needs attention',
  unknown: 'not enough data',
}

export function StatusPill({ status }: { status: Status }) {
  return <span className="status"><StatusDot status={status} />{LABELS[status]}</span>
}

export function StatusDot({ status, title }: { status: Status; title?: string }) {
  return <span className={`dot dot-${status}`} title={title ?? LABELS[status]} aria-label={title ?? LABELS[status]} />
}
