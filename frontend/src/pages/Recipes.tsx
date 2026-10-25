import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useRecipes, useSaveRecipe } from '../api/hooks'
import type { MealType, RecipeSummary } from '../api/types'
import { FavoriteStar } from '../components/FavoriteStar'
import {
  DIET_FILTER_OPTIONS,
  MEAL_TYPE_LABELS,
  dietBadge,
  dietFilterParams,
  tagsWorthShowing,
  type DietFilter,
} from '../lib/recipeLabels'
import {
  Button,
  Card,
  EmptyState,
  ErrorNote,
  Field,
  Input,
  Loading,
  Modal,
  PageHeader,
  Select,
  TextArea,
} from '../components/ui'

function NewRecipeForm({ onDone }: { onDone: () => void }) {
  const save = useSaveRecipe()
  const [title, setTitle] = useState('')
  const [servings, setServings] = useState('')
  const [minutes, setMinutes] = useState('')
  const [tags, setTags] = useState('')
  const [ingredients, setIngredients] = useState('')
  const [instructions, setInstructions] = useState('')

  const submit = (event: React.FormEvent) => {
    event.preventDefault()
    const lines = ingredients
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean)
    if (!title.trim() || lines.length === 0) return

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
        <Input autoFocus value={title} onChange={(e) => setTitle(e.target.value)} />
      </Field>
      <div className="grid grid-cols-3 gap-3">
        <Field label="Servings">
          <Input type="number" min="1" value={servings} onChange={(e) => setServings(e.target.value)} />
        </Field>
        <Field label="Minutes">
          <Input type="number" min="0" value={minutes} onChange={(e) => setMinutes(e.target.value)} />
        </Field>
        <Field label="Tags (comma separated)">
          <Input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="quick, vegan" />
        </Field>
      </div>
      <Field label="Ingredients (one per line)">
        <TextArea
          rows={6}
          value={ingredients}
          placeholder={'200 g pasta\n2 cloves garlic\n1 tbsp olive oil'}
          onChange={(e) => setIngredients(e.target.value)}
        />
      </Field>
      <p className="-mt-2 text-xs text-white/40">
        Quantities and units are parsed automatically, so write them naturally.
      </p>
      <Field label="Method">
        <TextArea rows={5} value={instructions} onChange={(e) => setInstructions(e.target.value)} />
      </Field>
      {save.isError && <ErrorNote error={save.error} />}
      <div className="flex justify-end gap-2">
        <Button variant="ghost" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" variant="primary" disabled={save.isPending}>
          {save.isPending ? 'Saving…' : 'Save recipe'}
        </Button>
      </div>
    </form>
  )
}

function RecipeBadges({ recipe }: { recipe: RecipeSummary }) {
  const badge = dietBadge(recipe.diet, recipe.meat_types)
  const meal = recipe.meal_type ? MEAL_TYPE_LABELS[recipe.meal_type] : null
  const tags = tagsWorthShowing(recipe.tags, recipe.meal_type).slice(0, 2)
  if (!badge && !meal && tags.length === 0) return null

  return (
    <div className="mt-2 flex flex-wrap gap-1">
      {badge && (
        <span
          className={`rounded-full px-2 py-0.5 text-xs ${
            badge.tone === 'green'
              ? 'bg-emerald-500/15 text-emerald-300'
              : 'bg-amber-500/10 text-amber-200/80'
          }`}
        >
          {badge.label}
        </span>
      )}
      {meal && meal !== 'Other' && (
        <span className="rounded-full bg-white/5 px-2 py-0.5 text-xs text-white/50">{meal}</span>
      )}
      {tags.map((tag) => (
        <span key={tag} className="rounded-full bg-white/5 px-2 py-0.5 text-xs text-white/40">
          {tag}
        </span>
      ))}
    </div>
  )
}

export default function Recipes() {
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(0)
  const [creating, setCreating] = useState(false)
  const [favoritesOnly, setFavoritesOnly] = useState(false)
  const [dietFilter, setDietFilter] = useState<DietFilter>('')
  const [mealType, setMealType] = useState<MealType | ''>('')
  const [sort, setSort] = useState<'title' | 'favorite'>('title')
  const limit = 24

  const { data, isLoading, error } = useRecipes({
    search,
    limit,
    offset: page * limit,
    favorites_only: favoritesOnly,
    ...dietFilterParams(dietFilter),
    meal_type: mealType || undefined,
    sort,
  })
  const pages = data ? Math.ceil(data.total / limit) : 0
  const filtered = Boolean(dietFilter || mealType || favoritesOnly)

  return (
    <>
      <PageHeader
        title="Recipes"
        subtitle={data ? `${data.total} recipe${data.total === 1 ? '' : 's'} indexed` : undefined}
        action={
          <div className="flex flex-wrap gap-2">
            <Input
              placeholder="Search recipes…"
              value={search}
              className="w-full sm:w-64"
              onChange={(e) => {
                setSearch(e.target.value)
                setPage(0)
              }}
            />
            <Select
              aria-label="Sort"
              value={sort}
              className="w-full sm:w-44"
              onChange={(e) => {
                setSort(e.target.value as 'title' | 'favorite')
                setPage(0)
              }}
            >
              <option value="title">Sort: A–Z</option>
              <option value="favorite">Sort: favourites first</option>
            </Select>
            <Select
              aria-label="Diet"
              value={dietFilter}
              className="w-full sm:w-44"
              onChange={(e) => {
                setDietFilter(e.target.value as DietFilter)
                setPage(0)
              }}
            >
              {DIET_FILTER_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
            <Select
              aria-label="Meal type"
              value={mealType}
              className="w-full sm:w-40"
              onChange={(e) => {
                setMealType(e.target.value as MealType | '')
                setPage(0)
              }}
            >
              <option value="">Any meal</option>
              {(Object.keys(MEAL_TYPE_LABELS) as MealType[]).map((m) => (
                <option key={m} value={m}>
                  {MEAL_TYPE_LABELS[m]}
                </option>
              ))}
            </Select>
            <Button
              variant={favoritesOnly ? 'primary' : 'secondary'}
              title="Show only favourites"
              onClick={() => {
                setFavoritesOnly((on) => !on)
                setPage(0)
              }}
            >
              ★ Favourites
            </Button>
            <Button variant="primary" onClick={() => setCreating(true)}>
              Add recipe
            </Button>
          </div>
        }
      />

      {isLoading && <Loading what="recipes" />}
      {error && <ErrorNote error={error} />}

      {data && data.items.length === 0 && (
        <EmptyState
          title={
            filtered || search
              ? 'No recipes match those filters'
              : 'No recipes yet'
          }
          hint={
            filtered || search
              ? 'Try widening the diet or meal filter, or clearing the search.'
              : 'Add one by hand, or run a recipe import from the Admin page.'
          }
        />
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {data?.items.map((recipe) => (
          <Link key={recipe.id} to={`/recipes/${recipe.id}`}>
            <Card className="h-full transition hover:border-emerald-500/40">
              {recipe.image_url && (
                <img
                  src={recipe.image_url}
                  alt=""
                  loading="lazy"
                  className="mb-3 h-32 w-full rounded-lg object-cover"
                />
              )}
              <div className="flex items-start justify-between gap-2">
                <p className="font-medium text-white">{recipe.title}</p>
                <FavoriteStar id={recipe.id} isFavorite={recipe.is_favorite} className="-mr-1 -mt-1" />
              </div>
              <p className="mt-1 text-xs text-white/40">
                {recipe.total_minutes ? `${recipe.total_minutes} min` : 'Time n/a'}
                {recipe.source_site ? ` · ${recipe.source_site}` : ''}
              </p>
              <RecipeBadges recipe={recipe} />
            </Card>
          </Link>
        ))}
      </div>

      {pages > 1 && (
        <div className="mt-6 flex items-center justify-center gap-3">
          <Button disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
            Previous
          </Button>
          <span className="text-sm text-white/40">
            Page {page + 1} of {pages}
          </span>
          <Button disabled={page + 1 >= pages} onClick={() => setPage((p) => p + 1)}>
            Next
          </Button>
        </div>
      )}

      {creating && (
        <Modal title="New recipe" onClose={() => setCreating(false)}>
          <NewRecipeForm onDone={() => setCreating(false)} />
        </Modal>
      )}
    </>
  )
}
