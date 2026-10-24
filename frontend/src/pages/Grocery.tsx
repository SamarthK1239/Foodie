import { useState } from 'react'
import {
  useAddGrocery,
  useClearPurchased,
  useDeleteGrocery,
  useGrocery,
  useUpdateGrocery,
} from '../api/hooks'
import type { GrocerySource } from '../api/types'
import { Button, Card, EmptyState, ErrorNote, Input, Loading, PageHeader } from '../components/ui'
import { formatQuantity } from '../lib/format'

const SOURCE_LABELS: Record<GrocerySource, string> = {
  auto_depleted: 'Ran out',
  recipe_gap: 'Recipe needed it',
  manual: 'Added by you',
  period_review: 'From your review',
}

export default function Grocery() {
  const [name, setName] = useState('')
  const [quantity, setQuantity] = useState('')
  const { data: pending, isLoading, error } = useGrocery('pending')
  const { data: purchased } = useGrocery('purchased')
  const add = useAddGrocery()
  const update = useUpdateGrocery()
  const remove = useDeleteGrocery()
  const clear = useClearPurchased()

  const submit = (event: React.FormEvent) => {
    event.preventDefault()
    if (!name.trim()) return
    add.mutate(
      {
        ingredient_name: name.trim(),
        quantity: quantity ? Number(quantity) : undefined,
      },
      {
        onSuccess: () => {
          setName('')
          setQuantity('')
        },
      },
    )
  }

  return (
    <>
      <PageHeader
        title="Grocery list"
        subtitle="Items are added automatically when you run out or a recipe comes up short"
      />

      <form onSubmit={submit} className="mb-6 flex gap-2">
        <Input
          placeholder="Add something…"
          value={name}
          className="max-w-sm"
          onChange={(e) => setName(e.target.value)}
        />
        <Input
          type="number"
          min="0"
          step="any"
          placeholder="Qty"
          value={quantity}
          className="w-24"
          onChange={(e) => setQuantity(e.target.value)}
        />
        <Button type="submit" variant="primary" disabled={add.isPending}>
          Add
        </Button>
      </form>

      {isLoading && <Loading what="your list" />}
      {error && <ErrorNote error={error} />}

      {pending && pending.length === 0 && (
        <EmptyState title="Nothing to buy" hint="Your grocery list is empty." />
      )}

      {pending && pending.length > 0 && (
        <Card className="py-0">
          {pending.map((item) => (
            <div
              key={item.id}
              className="flex items-center gap-3 border-b border-white/5 py-3 last:border-0"
            >
              <label className="flex min-h-11 min-w-11 cursor-pointer items-center justify-center md:min-h-0 md:min-w-0">
                <input
                  type="checkbox"
                  checked={false}
                  title="Mark as purchased"
                  className="h-5 w-5 accent-emerald-500 md:h-4 md:w-4"
                  onChange={() => update.mutate({ id: item.id, status: 'purchased' })}
                />
              </label>
              <div className="flex-1">
                <p className="text-sm font-medium text-white">
                  {item.label}
                  {item.quantity !== null && (
                    <span className="ml-2 text-white/50">
                      {formatQuantity(item.quantity, item.unit)}
                    </span>
                  )}
                </p>
                <p className="text-xs text-white/35">
                  {SOURCE_LABELS[item.source]}
                  {item.note ? ` · ${item.note}` : ''}
                </p>
              </div>
              <Button
                variant="ghost"
                title="Not needed"
                onClick={() => update.mutate({ id: item.id, status: 'dismissed' })}
              >
                Skip
              </Button>
              <Button variant="ghost" onClick={() => remove.mutate(item.id)}>
                ✕
              </Button>
            </div>
          ))}
        </Card>
      )}

      {purchased && purchased.length > 0 && (
        <section className="mt-8">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-white/50">
              Purchased ({purchased.length})
            </h2>
            <Button variant="ghost" onClick={() => clear.mutate()}>
              Clear
            </Button>
          </div>
          <Card className="py-0">
            {purchased.map((item) => (
              <div
                key={item.id}
                className="flex items-center gap-3 border-b border-white/5 py-2.5 last:border-0"
              >
                <span className="flex-1 text-sm text-white/40 line-through">{item.label}</span>
                <Button
                  variant="ghost"
                  onClick={() => update.mutate({ id: item.id, status: 'pending' })}
                >
                  Undo
                </Button>
              </div>
            ))}
          </Card>
        </section>
      )}
    </>
  )
}
