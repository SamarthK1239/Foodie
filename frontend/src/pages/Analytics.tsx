import { useSyncExternalStore } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import {
  useAnalyticsSeries,
  useAnalyticsSummary,
  useCookEvents,
  useSetLeftoverState,
} from '../api/hooks'
import { Button, Card, EmptyState, ErrorNote, Loading, PageHeader } from '../components/ui'

interface CategoryRow {
  category: string | null
  total: number
  count: number
}
interface PeriodRow {
  period: string
  total: number
}
interface WastedRow {
  name: string
  times: number
  cost: number
}
interface UsedRow {
  name: string
  times: number
}

const AXIS = { stroke: '#ffffff40', fontSize: 12 }
const TOOLTIP_STYLE = {
  background: '#141821',
  border: '1px solid rgba(255,255,255,0.1)',
  borderRadius: 8,
  fontSize: 12,
}

function Tile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <Card>
      <p className="text-xs uppercase tracking-wide text-white/40">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-white">{value}</p>
      {hint && <p className="mt-1 text-xs text-white/35">{hint}</p>}
    </Card>
  )
}

function ChartCard({
  title,
  empty,
  children,
}: {
  title: string
  empty: boolean
  children: React.ReactElement
}) {
  return (
    <Card>
      <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-white/50">{title}</h2>
      {empty ? (
        <p className="py-10 text-center text-sm text-white/35">Not enough data yet</p>
      ) : (
        <div className="h-60">
          <ResponsiveContainer width="100%" height="100%">
            {children}
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  )
}

function money(value: number) {
  return `£${value.toFixed(2)}`
}

// Category labels on vertical bar charts must not eat a third of a phone screen.
const NARROW_QUERY = '(max-width: 640px)'

function useNarrowViewport() {
  return useSyncExternalStore(
    (onChange) => {
      const media = window.matchMedia(NARROW_QUERY)
      media.addEventListener('change', onChange)
      return () => media.removeEventListener('change', onChange)
    },
    () => window.matchMedia(NARROW_QUERY).matches,
    () => false,
  )
}

export default function Analytics() {
  const narrow = useNarrowViewport()
  const labelWidth = narrow ? 72 : 110
  const truncateLabel = (value: string) =>
    narrow && value.length > 11 ? `${value.slice(0, 10)}…` : value
  const days = 28
  const { data: summary, isLoading, error } = useAnalyticsSummary(days)
  const { data: overTime } = useAnalyticsSeries<PeriodRow>('spend-over-time', days)
  const { data: byCategory } = useAnalyticsSeries<CategoryRow>('spend-by-category', days)
  const { data: mostWasted } = useAnalyticsSeries<WastedRow>('most-wasted', days)
  const { data: mostUsed } = useAnalyticsSeries<UsedRow>('most-used', days)
  const { data: cookEvents } = useCookEvents()
  const setLeftover = useSetLeftoverState()

  if (isLoading) return <Loading what="your stats" />
  if (error) return <ErrorNote error={error} />
  if (!summary) return null

  const categoryData = (byCategory ?? []).map((row) => ({
    ...row,
    label: row.category ?? 'Uncategorised',
  }))

  return (
    <>
      <PageHeader title="Insights" subtitle={`Last ${days} days`} />

      <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Tile
          label="Meals cooked"
          value={summary.dishes_cooked.toString()}
          hint={`${summary.items_consumed} items used up`}
        />
        <Tile
          label="Waste rate"
          value={`${Math.round(summary.waste_rate * 100)}%`}
          hint={`${summary.items_discarded} items binned`}
        />
        <Tile
          label="Spent"
          value={money(summary.total_spend)}
          hint={`${summary.items_purchased} items bought`}
        />
        <Tile
          label="Expiring soon"
          value={summary.expiring_soon.toString()}
          hint={`${summary.active_items} items in the kitchen`}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <ChartCard title="Spend per week" empty={!overTime?.length}>
          <LineChart data={overTime ?? []}>
            <CartesianGrid stroke="#ffffff10" vertical={false} />
            <XAxis dataKey="period" {...AXIS} />
            <YAxis {...AXIS} />
            <Tooltip
              contentStyle={TOOLTIP_STYLE}
              cursor={{ stroke: '#ffffff20' }}
              formatter={(value) => money(Number(value))}
            />
            <Line type="monotone" dataKey="total" stroke="#34d399" strokeWidth={2} dot={false} />
          </LineChart>
        </ChartCard>

        <ChartCard title="Spend by category" empty={!categoryData.length}>
          <BarChart data={categoryData}>
            <CartesianGrid stroke="#ffffff10" vertical={false} />
            <XAxis dataKey="label" {...AXIS} />
            <YAxis {...AXIS} />
            <Tooltip
              contentStyle={TOOLTIP_STYLE}
              cursor={{ fill: '#ffffff08' }}
              formatter={(value) => money(Number(value))}
            />
            <Bar dataKey="total" fill="#60a5fa" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ChartCard>

        <ChartCard title="Most wasted" empty={!mostWasted?.length}>
          <BarChart data={mostWasted ?? []} layout="vertical">
            <CartesianGrid stroke="#ffffff10" horizontal={false} />
            <XAxis type="number" {...AXIS} allowDecimals={false} />
            <YAxis
              type="category"
              dataKey="name"
              width={labelWidth}
              tickFormatter={truncateLabel}
              {...AXIS}
            />
            <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: '#ffffff08' }} />
            <Bar dataKey="times" fill="#f87171" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ChartCard>

        <ChartCard title="Most used" empty={!mostUsed?.length}>
          <BarChart data={mostUsed ?? []} layout="vertical">
            <CartesianGrid stroke="#ffffff10" horizontal={false} />
            <XAxis type="number" {...AXIS} allowDecimals={false} />
            <YAxis
              type="category"
              dataKey="name"
              width={labelWidth}
              tickFormatter={truncateLabel}
              {...AXIS}
            />
            <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: '#ffffff08' }} />
            <Bar dataKey="times" fill="#34d399" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ChartCard>
      </div>

      <section className="mt-8">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-white/50">
          Recently cooked
        </h2>
        {cookEvents && cookEvents.length === 0 && (
          <EmptyState title="No cook history" hint="Cook a recipe and it'll show up here." />
        )}
        {cookEvents && cookEvents.length > 0 && (
          <Card className="py-0">
            {cookEvents.map((event) => (
              <div
                key={event.id}
                className="flex items-center gap-3 border-b border-white/5 py-3 last:border-0"
              >
                <span className="flex-1 text-sm text-white/80">{event.recipe_title}</span>
                <span className="text-xs text-white/35">
                  {new Date(event.cooked_at).toLocaleDateString()}
                </span>
                {event.leftover_state === 'in_fridge' ? (
                  <Button
                    variant="ghost"
                    disabled={setLeftover.isPending}
                    onClick={() => setLeftover.mutate({ id: event.id, state: 'finished' })}
                  >
                    Leftovers in fridge — mark eaten
                  </Button>
                ) : (
                  <Button
                    variant="ghost"
                    disabled={setLeftover.isPending}
                    onClick={() => setLeftover.mutate({ id: event.id, state: 'in_fridge' })}
                  >
                    Saved leftovers?
                  </Button>
                )}
              </div>
            ))}
          </Card>
        )}
      </section>
    </>
  )
}
