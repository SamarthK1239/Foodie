import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  useAdminStats,
  useCancelIngest,
  useIngestStatus,
  useResolveUnmatched,
  useStartIngest,
  useUnmatched,
} from '../api/hooks'
import type { UnmatchedLine } from '../api/types'
import {
  Button,
  Card,
  EmptyState,
  ErrorNote,
  Field,
  Input,
  Loading,
  PageHeader,
  Select,
} from '../components/ui'

function UnmatchedRow({ line }: { line: UnmatchedLine }) {
  const resolve = useResolveUnmatched()
  const [name, setName] = useState(line.suggestion ?? '')

  return (
    <div className="flex flex-wrap items-center gap-3 border-b border-white/5 py-3 last:border-0">
      <div className="min-w-56 flex-1">
        <p className="text-sm text-white/80">{line.raw_text}</p>
        <Link
          to={`/recipes/${line.recipe_id}`}
          className="text-xs text-white/35 hover:text-emerald-400"
        >
          {line.recipe_title}
        </Link>
      </div>
      <Input
        value={name}
        placeholder="Ingredient name"
        className="w-52"
        onChange={(e) => setName(e.target.value)}
      />
      <Button
        variant="primary"
        disabled={!name.trim() || resolve.isPending}
        onClick={() =>
          resolve.mutate({ recipe_ingredient_id: line.recipe_ingredient_id, ingredient_name: name.trim() })
        }
      >
        Link
      </Button>
    </div>
  )
}

export default function Admin() {
  const { data: stats } = useAdminStats()
  const [mode, setMode] = useState('new_only')
  const [maxRecipes, setMaxRecipes] = useState('200')

  const start = useStartIngest()
  const cancel = useCancelIngest()
  const { data: status, isLoading } = useIngestStatus(true)
  const { data: unmatched } = useUnmatched()

  const job = status?.job
  const running = status?.running ?? false

  return (
    <>
      <PageHeader title="Admin" subtitle="Recipe imports and data maintenance" />

      {stats && (
        <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[
            ['Recipes', stats.recipes.toString()],
            ['Ingredients', stats.ingredients.toString()],
            ['Unlinked recipe lines', stats.unmatched_recipe_lines.toString()],
          ].map(([label, value]) => (
            <Card key={label}>
              <p className="text-xs uppercase tracking-wide text-white/40">{label}</p>
              <p className="mt-1 text-2xl font-semibold text-white">{value}</p>
            </Card>
          ))}
          <Card>
            <p className="text-xs uppercase tracking-wide text-white/40">Database</p>
            <p className="mt-1 break-all text-xs text-white/60">{stats.database_path}</p>
          </Card>
        </div>
      )}

      <Card className="mb-6">
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-white/50">
          Recipe import
        </h2>

        {isLoading && <Loading what="import status" />}

        <div className="flex flex-wrap items-end gap-3">
          <Field label="Mode">
            <Select value={mode} className="w-56" onChange={(e) => setMode(e.target.value)}>
              <option value="new_only">New recipes only</option>
              <option value="revalidate">Refresh existing recipes</option>
            </Select>
          </Field>
          <Field label="Max recipes">
            <Input
              type="number"
              min="1"
              className="w-32"
              value={maxRecipes}
              onChange={(e) => setMaxRecipes(e.target.value)}
            />
          </Field>
          {running ? (
            <Button variant="danger" onClick={() => cancel.mutate()}>
              Stop import
            </Button>
          ) : (
            <Button
              variant="primary"
              disabled={start.isPending}
              onClick={() => start.mutate({ mode, max_recipes: Number(maxRecipes) || 100 })}
            >
              Start import
            </Button>
          )}
        </div>

        {start.isError && (
          <div className="mt-3">
            <ErrorNote error={start.error} />
          </div>
        )}

        {status && (
          <p className="mt-3 text-xs text-white/35">
            Sites: {status.configured_sites.join(', ') || 'none configured'}
          </p>
        )}

        {job && (
          <div className="mt-4 rounded-lg border border-white/10 bg-white/[0.03] p-4">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium text-white">
                {job.mode} · {job.status}
                {running && <span className="ml-2 text-emerald-400">running…</span>}
              </p>
              <p className="text-xs text-white/35">
                started {new Date(job.started_at).toLocaleString()}
              </p>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
              <span className="text-white/60">
                Found <span className="text-white">{job.discovered_count}</span>
              </span>
              <span className="text-white/60">
                Imported <span className="text-emerald-400">{job.imported_count}</span>
              </span>
              <span className="text-white/60">
                Skipped <span className="text-white">{job.skipped_count}</span>
              </span>
              <span className="text-white/60">
                Failed <span className="text-red-400">{job.failed_count}</span>
              </span>
            </div>
            {job.target_count > 0 && (
              <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-white/10">
                <div
                  className="h-full bg-emerald-500 transition-all"
                  style={{
                    width: `${Math.min(100, (job.imported_count / job.target_count) * 100)}%`,
                  }}
                />
              </div>
            )}
            {job.last_error && (
              <p className="mt-3 text-xs text-amber-400">Last error: {job.last_error}</p>
            )}
          </div>
        )}
      </Card>

      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-white/50">
          Unlinked ingredients
        </h2>
        <p className="mb-3 text-sm text-white/40">
          These recipe lines could not be matched to a known ingredient, so they never count towards
          suggestions. Give each one a name to link it.
        </p>
        {unmatched && unmatched.length === 0 && (
          <EmptyState title="Everything is linked" hint="No action needed." />
        )}
        {unmatched && unmatched.length > 0 && (
          <Card className="py-0">
            {unmatched.map((line) => (
              <UnmatchedRow key={line.recipe_ingredient_id} line={line} />
            ))}
          </Card>
        )}
      </section>
    </>
  )
}
