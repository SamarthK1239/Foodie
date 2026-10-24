import type { ExpiryBucket } from '../api/types'

export const BUCKET_STYLES: Record<ExpiryBucket, { label: string; chip: string; dot: string }> = {
  expired: {
    label: 'Expired',
    chip: 'bg-red-500/15 text-red-300 border-red-500/30',
    dot: 'bg-red-400',
  },
  critical: {
    label: 'Use now',
    chip: 'bg-orange-500/15 text-orange-300 border-orange-500/30',
    dot: 'bg-orange-400',
  },
  soon: {
    label: 'Use soon',
    chip: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
    dot: 'bg-amber-400',
  },
  ok: {
    label: 'Fresh',
    chip: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
    dot: 'bg-emerald-400',
  },
  none: {
    label: 'No date',
    chip: 'bg-white/10 text-white/50 border-white/15',
    dot: 'bg-white/30',
  },
}

export const BUCKET_ORDER: ExpiryBucket[] = ['expired', 'critical', 'soon', 'ok', 'none']

export function formatDaysLeft(daysLeft: number | null): string {
  if (daysLeft === null) return 'No expiry set'
  if (daysLeft < 0) return `Expired ${Math.abs(daysLeft)}d ago`
  if (daysLeft === 0) return 'Expires today'
  if (daysLeft === 1) return 'Expires tomorrow'
  return `${daysLeft}d left`
}

export function formatQuantity(quantity: number, unit: string | null): string {
  const rounded = Math.round(quantity * 100) / 100
  if (!unit || unit === 'unit') return `${rounded}`
  return `${rounded} ${unit}`
}
