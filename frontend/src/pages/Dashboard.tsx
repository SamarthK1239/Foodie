import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  useAddItem,
  useAdjustItem,
  useDeleteItem,
  useInventory,
  useInventorySummary,
  useItemAction,
  useUpdateItem,
} from '../api/hooks'
import type { InventoryItem } from '../api/types'
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
} from '../components/ui'
import { LOCATIONS, UNITS } from '../lib/constants'
import { ExpiryChip } from '../components/ExpiryChip'
import { BUCKET_ORDER, BUCKET_STYLES, formatQuantity } from '../lib/format'


function AddItemForm({ onDone }: { onDone: () => void }) {
  const addItem = useAddItem()
  const [form, setForm] = useState({
    ingredient_name: '',
    quantity: '1',
    unit: 'unit',
    expiry_date: '',
    location: 'fridge',
    cost: '',
  })

  const update = (key: string, value: string) => setForm((f) => ({ ...f, [key]: value }))

  const submit = (event: React.FormEvent) => {
    event.preventDefault()
    const quantity = Number(form.quantity)
    if (!form.ingredient_name.trim() || !Number.isFinite(quantity) || quantity <= 0) return
    addItem.mutate(
      {
        ingredient_name: form.ingredient_name.trim(),
        quantity,
        unit: form.unit,
        expiry_date: form.expiry_date || undefined,
        location: form.location,
        cost: form.cost ? Number(form.cost) : undefined,
      },
      { onSuccess: onDone },
    )
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <Field label="Item">
        <Input
          autoFocus
          placeholder="e.g. Tomatoes"
          value={form.ingredient_name}
          onChange={(e) => update('ingredient_name', e.target.value)}
        />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Quantity">
          <Input
            type="number"
            min="0"
            step="any"
            value={form.quantity}
            onChange={(e) => update('quantity', e.target.value)}
          />
        </Field>
        <Field label="Unit">
          <Select value={form.unit} onChange={(e) => update('unit', e.target.value)}>
            {UNITS.map((unit) => (
              <option key={unit} value={unit}>
                {unit}
              </option>
            ))}
          </Select>
        </Field>
      </div>
      <div className="grid grid-cols-3 gap-3">
        <Field label="Expires">
          <Input
            type="date"
            value={form.expiry_date}
            onChange={(e) => update('expiry_date', e.target.value)}
          />
        </Field>
        <Field label="Location">
          <Select value={form.location} onChange={(e) => update('location', e.target.value)}>
            {LOCATIONS.map((loc) => (
              <option key={loc} value={loc}>
                {loc}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Cost">
          <Input
            type="number"
            min="0"
            step="0.01"
            placeholder="0.00"
            value={form.cost}
            onChange={(e) => update('cost', e.target.value)}
          />
        </Field>
      </div>
      {addItem.isError && <ErrorNote error={addItem.error} />}
      <div className="flex justify-end gap-2">
        <Button variant="ghost" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" variant="primary" disabled={addItem.isPending}>
          {addItem.isPending ? 'Adding…' : 'Add item'}
        </Button>
      </div>
    </form>
  )
}

function ItemRow({ item }: { item: InventoryItem }) {
  const adjust = useAdjustItem()
  const update = useUpdateItem()
  const discard = useItemAction('discard')
  const finish = useItemAction('finish')
  const remove = useDeleteItem()
  const [editing, setEditing] = useState(false)
  const [expiry, setExpiry] = useState(item.expiry_date ?? '')

  const step = item.unit === 'unit' ? 1 : item.quantity >= 100 ? 50 : 1

  return (
    <div className="flex flex-wrap items-center gap-3 border-b border-white/5 py-3 last:border-0">
      <div className="min-w-48 flex-1">
        <p className="font-medium text-white">{item.ingredient.display_name}</p>
        <p className="text-xs text-white/40">
          {item.location}
          {item.ingredient.category ? ` · ${item.ingredient.category}` : ''}
        </p>
      </div>

      <div className="flex items-center gap-1.5">
        <Button
          variant="ghost"
          title="Use some"
          onClick={() => adjust.mutate({ id: item.id, delta: -step, reason: 'cook' })}
        >
          −
        </Button>
        <span className="min-w-20 text-center text-sm tabular-nums text-white/80">
          {formatQuantity(item.quantity, item.unit)}
        </span>
        <Button
          variant="ghost"
          title="Add more"
          onClick={() => adjust.mutate({ id: item.id, delta: step, reason: 'purchase' })}
        >
          +
        </Button>
      </div>

      {editing ? (
        <div className="flex items-center gap-2">
          <Input
            type="date"
            value={expiry}
            className="w-40"
            onChange={(e) => setExpiry(e.target.value)}
          />
          <Button
            variant="primary"
            onClick={() => {
              update.mutate({ id: item.id, expiry_date: expiry || null })
              setEditing(false)
            }}
          >
            Save
          </Button>
        </div>
      ) : (
        <button
          onClick={() => setEditing(true)}
          title="Edit expiry date"
          className="inline-flex min-h-11 items-center md:min-h-0"
        >
          <ExpiryChip bucket={item.expiry_bucket} daysLeft={item.days_left} />
        </button>
      )}

      <div className="flex gap-1.5">
        <Button variant="ghost" title="All used up" onClick={() => finish.mutate(item.id)}>
          Finished
        </Button>
        <Button variant="danger" title="Threw it away" onClick={() => discard.mutate(item.id)}>
          Binned
        </Button>
        <Button variant="ghost" title="Remove entry" onClick={() => remove.mutate(item.id)}>
          ✕
        </Button>
      </div>
    </div>
  )
}

export default function Dashboard() {
  const [search, setSearch] = useState('')
  const [adding, setAdding] = useState(false)
  const { data: items, isLoading, error } = useInventory({ search })
  const { data: summary } = useInventorySummary()

  const grouped = useMemo(() => {
    const groups = new Map<string, InventoryItem[]>()
    for (const item of items ?? []) {
      const list = groups.get(item.expiry_bucket) ?? []
      list.push(item)
      groups.set(item.expiry_bucket, list)
    }
    return groups
  }, [items])

  return (
    <>
      <PageHeader
        title="Kitchen"
        subtitle="What you have, sorted by what needs using first"
        action={
          <div className="flex gap-2">
            <Input
              placeholder="Search items…"
              value={search}
              className="w-56"
              onChange={(e) => setSearch(e.target.value)}
            />
            <Button variant="primary" onClick={() => setAdding(true)}>
              Add item
            </Button>
          </div>
        }
      />

      {summary && (
        <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-5">
          {BUCKET_ORDER.map((bucket) => (
            <Card key={bucket}>
              <p className="text-xs uppercase tracking-wide text-white/40">
                {BUCKET_STYLES[bucket].label}
              </p>
              <p className="mt-1 text-2xl font-semibold text-white">
                {summary.buckets[bucket] ?? 0}
              </p>
            </Card>
          ))}
        </div>
      )}

      {isLoading && <Loading what="your kitchen" />}
      {error && <ErrorNote error={error} />}

      {items && items.length === 0 && (
        <EmptyState
          title="Nothing in the kitchen yet"
          hint="Add what's in your fridge and Foodie will start suggesting meals."
        />
      )}

      <div className="space-y-6">
        {BUCKET_ORDER.filter((bucket) => grouped.has(bucket)).map((bucket) => (
          <section key={bucket}>
            <h2 className="mb-2 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-white/50">
              <span className={`h-2 w-2 rounded-full ${BUCKET_STYLES[bucket].dot}`} />
              {BUCKET_STYLES[bucket].label}
              <span className="text-white/30">({grouped.get(bucket)!.length})</span>
            </h2>
            <Card className="py-0">
              {grouped.get(bucket)!.map((item) => (
                <ItemRow key={item.id} item={item} />
              ))}
            </Card>
          </section>
        ))}
      </div>

      {(summary?.buckets.expired ?? 0) + (summary?.buckets.critical ?? 0) > 0 && (
        <Card className="mt-6 border-emerald-500/20 bg-emerald-500/5">
          <p className="text-sm text-white/70">
            Some items need using up.{' '}
            <Link to="/suggestions" className="font-medium text-emerald-400 hover:underline">
              See what you can cook →
            </Link>
          </p>
        </Card>
      )}

      {adding && (
        <Modal title="Add to kitchen" onClose={() => setAdding(false)}>
          <AddItemForm onDone={() => setAdding(false)} />
        </Modal>
      )}
    </>
  )
}
