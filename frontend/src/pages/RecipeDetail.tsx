import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useCook, useDeleteRecipe, useRecipe, useSaveRecipe } from '../api/hooks'
import type { CookResult } from '../api/types'
import {
  Button,
  Card,
  ErrorNote,
  Field,
  Input,
  Loading,
  Modal,
  PageHeader,
  TextArea,
} from '../components/ui'
import { formatQuantity } from '../lib/format'

function EditForm({
  recipe,
  onDone,
}: {
  recipe: NonNullable<ReturnType<typeof useRecipe>['data']>
  onDone: () => void
}) {
  const save = useSaveRecipe(recipe.id)
  const [title, setTitle] = useState(recipe.title)
  const [servings, setServings] = useState(recipe.servings?.toString() ?? '')
  const [minutes, setMinutes] = useState(recipe.total_minutes?.toString() ?? '')
  const [tags, setTags] = useState(recipe.tags.join(', '))
  const [ingredients, setIngredients] = useState(
    recipe.ingredients.map((i) => i.raw_text).join('\n'),
  )
  const [instructions, setInstructions] = useState(recipe.instructions)

  const submit = (event: React.FormEvent) => {
    event.preventDefault()
    const lines = ingredients
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean)
    save.mutate(
      {
        title: title.trim(),
        instructions,
        servings: servings ? Number(servings) : null,
        total_minutes: minutes ? Number(minutes) : null,
        tags: tags
          .split(',')
          .map((t) => t.trim())
          .filter(Boolean),
        ingredients: lines.map((raw_text) => ({ raw_text, optional: false })),
      },
      { onSuccess: onDone },
    )
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <Field label="Title">
        <Input value={title} onChange={(e) => setTitle(e.target.value)} />
      </Field>
      <div className="grid grid-cols-3 gap-3">
        <Field label="Servings">
          <Input type="number" value={servings} onChange={(e) => setServings(e.target.value)} />
        </Field>
        <Field label="Minutes">
          <Input type="number" value={minutes} onChange={(e) => setMinutes(e.target.value)} />
        </Field>
        <Field label="Tags">
          <Input value={tags} onChange={(e) => setTags(e.target.value)} />
        </Field>
      </div>
      <Field label="Ingredients (one per line)">
        <TextArea rows={8} value={ingredients} onChange={(e) => setIngredients(e.target.value)} />
      </Field>
      <Field label="Method">
        <TextArea rows={8} value={instructions} onChange={(e) => setInstructions(e.target.value)} />
      </Field>
      <p className="-mt-2 text-xs text-white/40">
        Saving marks this recipe as hand-edited, so future re-imports will not overwrite it.
      </p>
      {save.isError && <ErrorNote error={save.error} />}
      <div className="flex justify-end gap-2">
        <Button variant="ghost" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" variant="primary" disabled={save.isPending}>
          {save.isPending ? 'Saving…' : 'Save changes'}
        </Button>
      </div>
    </form>
  )
}

export default function RecipeDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const recipeId = id ? Number(id) : undefined
  const { data: recipe, isLoading, error } = useRecipe(recipeId)
  const cook = useCook()
  const remove = useDeleteRecipe()
  const [editing, setEditing] = useState(false)
  const [multiplier, setMultiplier] = useState('1')
  const [result, setResult] = useState<CookResult | null>(null)

  if (isLoading) return <Loading what="recipe" />
  if (error) return <ErrorNote error={error} />
  if (!recipe) return null

  return (
    <>
      <Link to="/recipes" className="mb-4 inline-block text-sm text-white/40 hover:text-white">
        ← Back to recipes
      </Link>

      <PageHeader
        title={recipe.title}
        subtitle={[
          recipe.total_minutes ? `${recipe.total_minutes} min` : null,
          recipe.servings ? `serves ${recipe.servings}` : null,
          recipe.source_site,
        ]
          .filter(Boolean)
          .join(' · ')}
        action={
          <div className="flex items-center gap-2">
            <Input
              type="number"
              min="0.25"
              step="0.25"
              value={multiplier}
              className="w-20"
              title="Batch multiplier"
              onChange={(e) => setMultiplier(e.target.value)}
            />
            <Button
              variant="primary"
              disabled={cook.isPending}
              onClick={() =>
                cook.mutate(
                  { id: recipe.id, multiplier: Number(multiplier) || 1 },
                  { onSuccess: setResult },
                )
              }
            >
              {cook.isPending ? 'Cooking…' : 'I cooked this'}
            </Button>
            <Button onClick={() => setEditing(true)}>Edit</Button>
            <Button
              variant="danger"
              onClick={() => remove.mutate(recipe.id, { onSuccess: () => navigate('/recipes') })}
            >
              Delete
            </Button>
          </div>
        }
      />

      {result && (
        <Card className="mb-6 border-emerald-500/30 bg-emerald-500/5">
          <p className="font-medium text-emerald-300">Kitchen updated</p>
          {result.consumed.length > 0 && (
            <p className="mt-1 text-sm text-white/60">
              Used:{' '}
              {result.consumed
                .map((c) => `${c.ingredient} (${formatQuantity(c.quantity, c.unit)})`)
                .join(', ')}
            </p>
          )}
          {result.missing.length > 0 && (
            <p className="mt-1 text-sm text-white/60">
              You were missing: {result.missing.join(', ')} — added to your grocery list.
            </p>
          )}
        </Card>
      )}
      {cook.isError && <ErrorNote error={cook.error} />}

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-1">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-white/50">
            Ingredients
          </h2>
          <ul className="space-y-2">
            {recipe.ingredients.map((line) => (
              <li key={line.id} className="text-sm text-white/80">
                {line.raw_text}
                {line.optional && <span className="ml-1 text-xs text-white/35">(optional)</span>}
                {!line.ingredient && (
                  <span
                    className="ml-1 text-xs text-amber-400/70"
                    title="Not linked to a known ingredient, so it won't count towards suggestions"
                  >
                    ⚠
                  </span>
                )}
              </li>
            ))}
          </ul>
        </Card>

        <Card className="lg:col-span-2">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-white/50">
            Method
          </h2>
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-white/80">
            {recipe.instructions || 'No method recorded.'}
          </p>
          {recipe.source_url && (
            <a
              href={recipe.source_url}
              target="_blank"
              rel="noreferrer"
              className="mt-4 inline-block text-sm text-emerald-400 hover:underline"
            >
              View original source →
            </a>
          )}
        </Card>
      </div>

      {editing && (
        <Modal title="Edit recipe" onClose={() => setEditing(false)}>
          <EditForm recipe={recipe} onDone={() => setEditing(false)} />
        </Modal>
      )}
    </>
  )
}
