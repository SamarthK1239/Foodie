import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useCook, useExpiring, useSuggestions } from '../api/hooks'
import type { CookResult, Match, Suggestion } from '../api/types'
import { Button, Card, EmptyState, ErrorNote, Loading, PageHeader, Select } from '../components/ui'
import { ExpiryChip } from '../components/ExpiryChip'
import { formatQuantity } from '../lib/format'

function MatchPill({ match, missing }: { match: Match; missing?: boolean }) {
  const tone = missing
    ? 'border-white/10 bg-white/5 text-white/50'
    : match.urgency > 0.5
      ? 'border-amber-500/30 bg-amber-500/10 text-amber-200'
      : 'border-emerald-500/25 bg-emerald-500/10 text-emerald-200'

  const detail =
    match.quantity_needed !== null
      ? ` ${formatQuantity(match.quantity_needed, match.unit)}`
      : ''

  return (
    <span className={`rounded-full border px-2 py-0.5 text-xs ${tone}`} title={match.raw_text}>
      {match.name}
      {detail}
      {!missing && !match.sufficient && ' (low)'}
    </span>
  )
}

function CookSummary({ result, onClose }: { result: CookResult; onClose: () => void }) {
  return (
    <Card className="mb-6 border-emerald-500/30 bg-emerald-500/5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="font-medium text-emerald-300">Cooked {result.recipe_title}</p>
          {result.consumed.length > 0 && (
            <p className="mt-1 text-sm text-white/60">
              Used:{' '}
              {result.consumed
                .map((c) => `${c.ingredient} (${formatQuantity(c.quantity, c.unit)})`)
                .join(', ')}
            </p>
          )}
          {result.grocery_added.length > 0 && (
            <p className="mt-1 text-sm text-white/60">
              Added to grocery list: {result.grocery_added.join(', ')}
            </p>
          )}
        </div>
        <Button variant="ghost" onClick={onClose}>
          Dismiss
        </Button>
      </div>
    </Card>
  )
}

function SuggestionCard({
  suggestion,
  onCooked,
}: {
  suggestion: Suggestion
  onCooked: (result: CookResult) => void
}) {
  const cook = useCook()
  const coveragePercent = Math.round(suggestion.coverage * 100)
  const complete = suggestion.missing.length === 0

  return (
    <Card className="flex flex-col">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <Link
            to={`/recipes/${suggestion.recipe.id}`}
            className="font-medium text-white hover:text-emerald-400"
          >
            {suggestion.recipe.title}
          </Link>
          <p className="mt-0.5 text-xs text-white/40">
            {suggestion.recipe.total_minutes ? `${suggestion.recipe.total_minutes} min` : 'Time n/a'}
            {suggestion.recipe.servings ? ` · serves ${suggestion.recipe.servings}` : ''}
            {suggestion.recently_cooked ? ' · cooked recently' : ''}
          </p>
        </div>
        <span
          className={`shrink-0 rounded-full border px-2 py-0.5 text-xs font-medium ${
            complete
              ? 'border-emerald-500/30 bg-emerald-500/15 text-emerald-300'
              : 'border-white/15 bg-white/5 text-white/60'
          }`}
        >
          {coveragePercent}% ready
        </span>
      </div>

      {suggestion.urgency > 0.4 && (
        <p className="mb-2 text-xs font-medium text-amber-300">
          Uses ingredients that need eating soon
        </p>
      )}

      <div className="mb-3 flex flex-wrap gap-1.5">
        {suggestion.have.map((match) => (
          <MatchPill key={match.raw_text} match={match} />
        ))}
      </div>

      {suggestion.missing.length > 0 && (
        <div className="mb-3">
          <p className="mb-1 text-xs uppercase tracking-wide text-white/35">
            Missing {suggestion.missing.length}
          </p>
          <div className="flex flex-wrap gap-1.5">
            {suggestion.missing.map((match) => (
              <MatchPill key={match.raw_text} match={match} missing />
            ))}
          </div>
        </div>
      )}

      <div className="mt-auto flex gap-2 pt-2">
        <Button
          variant={complete ? 'primary' : 'secondary'}
          disabled={cook.isPending}
          onClick={() =>
            cook.mutate({ id: suggestion.recipe.id }, { onSuccess: (result) => onCooked(result) })
          }
        >
          {cook.isPending ? 'Cooking…' : complete ? 'Cook this' : 'Cook anyway'}
        </Button>
        <Link
          to={`/recipes/${suggestion.recipe.id}`}
          className="inline-flex min-h-11 items-center justify-center rounded-lg px-3 py-2 text-sm font-medium text-white/60 transition hover:bg-white/10 hover:text-white md:min-h-0 md:py-1.5"
        >
          View recipe
        </Link>
      </div>
      {cook.isError && (
        <div className="mt-2">
          <ErrorNote error={cook.error} />
        </div>
      )}
    </Card>
  )
}

export default function Suggestions() {
  const [minCoverage, setMinCoverage] = useState('0')
  const [page, setPage] = useState(0)
  const [cooked, setCooked] = useState<CookResult | null>(null)
  const limit = 9

  const { data, isLoading, error, refetch, isFetching } = useSuggestions({
    limit,
    offset: page * limit,
    min_coverage: Number(minCoverage),
  })
  const { data: expiring } = useExpiring(3)

  return (
    <>
      <PageHeader
        title="What can I cook?"
        subtitle="Ranked by what you have and what needs eating first"
        action={
          <div className="flex items-center gap-2">
            <Select
              value={minCoverage}
              className="w-44"
              onChange={(e) => {
                setMinCoverage(e.target.value)
                setPage(0)
              }}
            >
              <option value="0">Anything I can part-make</option>
              <option value="0.5">At least half the items</option>
              <option value="0.99">Only complete recipes</option>
            </Select>
            <Button
              variant="secondary"
              onClick={() => {
                setPage((p) => p + 1)
                void refetch()
              }}
            >
              Show different
            </Button>
          </div>
        }
      />

      {cooked && <CookSummary result={cooked} onClose={() => setCooked(null)} />}

      {expiring && expiring.length > 0 && (
        <Card className="mb-6 border-amber-500/20 bg-amber-500/5">
          <p className="mb-2 text-sm font-medium text-amber-200">Use these first</p>
          <div className="flex flex-wrap gap-2">
            {expiring.map((item) => (
              <span key={item.id} className="flex items-center gap-2 text-sm text-white/70">
                {item.ingredient.display_name}
                <ExpiryChip bucket={item.expiry_bucket} daysLeft={item.days_left} />
              </span>
            ))}
          </div>
        </Card>
      )}

      {isLoading && <Loading what="suggestions" />}
      {error && <ErrorNote error={error} />}

      {data && data.length === 0 && (
        <EmptyState
          title={page > 0 ? 'No more suggestions' : 'No suggestions yet'}
          hint={
            page > 0
              ? 'Go back to the first page to see the best matches.'
              : 'Add items to your kitchen and make sure some recipes are indexed.'
          }
        />
      )}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {data?.map((suggestion) => (
          <SuggestionCard
            key={suggestion.recipe.id}
            suggestion={suggestion}
            onCooked={setCooked}
          />
        ))}
      </div>

      {page > 0 && (
        <div className="mt-6 flex justify-center">
          <Button
            onClick={() => {
              setPage(0)
              void refetch()
            }}
            disabled={isFetching}
          >
            Back to best matches
          </Button>
        </div>
      )}
    </>
  )
}
