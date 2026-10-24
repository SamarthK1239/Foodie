import type { ExpiryBucket } from '../api/types'
import { BUCKET_STYLES, formatDaysLeft } from '../lib/format'

export function ExpiryChip({ bucket, daysLeft }: { bucket: ExpiryBucket; daysLeft: number | null }) {
  const style = BUCKET_STYLES[bucket]
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium ${style.chip}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${style.dot}`} />
      {formatDaysLeft(daysLeft)}
    </span>
  )
}
