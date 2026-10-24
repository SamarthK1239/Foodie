import { useState } from 'react'
import { Link } from 'react-router-dom'
import { usePeriodReview, useApplyPeriodReview } from '../api/hooks'
import type { PeriodReviewSuggestion } from '../api/types'
import {
  Button,
  Card,
  EmptyState,
  ErrorNote,
  Loading,
  PageHeader,
  Select,
} from '../components/ui'

function Section({
  title,
  hint,
  children,
}: {
  title: string
  hint: string
  children: React.ReactNode
}) {
  return (
    <section className="mt-8">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-white/50">{title}</h2>
      <p className="mb-3 mt-1 text-sm text-white/40">{hint}</p>
      {children}
    </section>
  )
}

function Row({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-3 border-b border-white/5 py-3 last:border-0">
      {children}
    </div>
  )
}

export default function Review() {
  const [weeks, setWeeks] = useState(2)
  const [picked, setPicked] = useState<Set<number>>(new Set())
  const { data, isLoading, error } = usePeriodReview(weeks)
  const apply = useApplyPeriodReview()

  const toggle = (id: number) =>
    setPicked((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  const describe = (row: PeriodReviewSuggestion) => {
    const stock =
      row.reason === 'out_of_stock'
        ? 'out of stock'
        : `${row.remaining}${row.unit ? ` ${row.unit}` : ''} left`
    const times = `used ${row.times_used}×`
    return row.already_on_list ? `${times} · ${stock} · already on your list` : `${times} · ${stock}`
  }

  return (
    <div>
      <PageHeader
        title="Period review"
        subtitle="What you actually ate, what went to waste, and what to buy next"
        action={
          <Select
            className="w-auto"
            value={weeks}
            onChange={(event) => setWeeks(Number(event.target.value))}
          >
            <option value={1}>Last week</option>
            <option value={2}>Last 2 weeks</option>
            <option value={4}>Last 4 weeks</option>
          </Select>
        }
      />

      {isLoading && <Loading what="your review" />}
      {error && <ErrorNote error={error} />}

      {data && (
        <>
          <Section
            title="Buy again"
            hint="Things you cooked with that have now run out. Anything you binned this period is left off on purpose."
          >
            {data.suggested.length === 0 ? (
              <EmptyState
                title="Nothing to restock"
                hint="You still have stock of everything you cooked with."
              />
            ) : (
              <>
                <Card className="py-0">
                  {data.suggested.map((row) => (
                    <Row key={row.ingredient_id}>
                      <label className="flex min-h-11 min-w-11 cursor-pointer items-center justify-center md:min-h-0 md:min-w-0">
                        <input
                          type="checkbox"
                          className="h-5 w-5 accent-emerald-500 md:h-4 md:w-4"
                          checked={picked.has(row.ingredient_id)}
                          onChange={() => toggle(row.ingredient_id)}
                        />
                      </label>
                      <div className="flex-1">
                        <p className="text-sm font-medium text-white">{row.name}</p>
                        <p className="text-xs text-white/35">{describe(row)}</p>
                      </div>
                    </Row>
                  ))}
                </Card>
                <div className="mt-3 flex flex-wrap items-center gap-3">
                  <Button
                    variant="primary"
                    disabled={picked.size === 0 || apply.isPending}
                    onClick={() =>
                      apply.mutate([...picked], { onSuccess: () => setPicked(new Set()) })
                    }
                  >
                    {apply.isPending ? 'Adding…' : `Add ${picked.size || ''} to grocery list`.trim()}
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() =>
                      setPicked(new Set(data.suggested.map((row) => row.ingredient_id)))
                    }
                  >
                    Select all
                  </Button>
                  <Link to="/grocery" className="text-sm text-white/50 hover:text-white">
                    View grocery list
                  </Link>
                </div>
                {apply.isSuccess && picked.size === 0 && (
                  <p className="mt-2 text-sm text-emerald-400">Added to your grocery list.</p>
                )}
              </>
            )}
          </Section>

          <Section
            title="Sitting untouched"
            hint="Already in the kitchen before this period began and never used since. Cook these before they turn into waste."
          >
            {data.unused.length === 0 ? (
              <EmptyState title="Nothing forgotten" hint="Everything in stock is recent or in use." />
            ) : (
              <Card className="py-0">
                {data.unused.map((row) => (
                  <Row key={row.item_id}>
                    <span className="flex-1 text-sm text-white/80">{row.name}</span>
                    <span className="text-xs text-white/35">
                      {row.quantity}
                      {row.unit ? ` ${row.unit}` : ''} · {row.days_in_stock} days in stock
                    </span>
                  </Row>
                ))}
              </Card>
            )}
          </Section>

          <Section title="Used" hint="What you actually cooked with over this period.">
            {data.used.length === 0 ? (
              <EmptyState title="No cooking recorded" hint="Cook a recipe and it'll show up here." />
            ) : (
              <Card className="py-0">
                {data.used.map((row) => (
                  <Row key={row.ingredient_id}>
                    <span className="flex-1 text-sm text-white/80">{row.name}</span>
                    <span className="text-xs text-white/35">{row.times}×</span>
                  </Row>
                ))}
              </Card>
            )}
          </Section>

          <Section title="Wasted" hint="Binned during this period. These are the ones costing you money.">
            {data.wasted.length === 0 ? (
              <EmptyState title="Nothing wasted" hint="Nothing went in the bin this period." />
            ) : (
              <Card className="py-0">
                {data.wasted.map((row) => (
                  <Row key={row.ingredient_id}>
                    <span className="flex-1 text-sm text-white/80">{row.name}</span>
                    <span className="text-xs text-red-300/70">
                      {row.times}× {row.cost > 0 ? `· £${row.cost.toFixed(2)}` : ''}
                    </span>
                  </Row>
                ))}
              </Card>
            )}
          </Section>
        </>
      )}
    </div>
  )
}
