import { useEffect, useRef, useState } from 'react'
import { useLookupBarcode, useScanToInventory } from '../api/hooks'
import type { ScanProduct } from '../api/types'
import {
  Button,
  Card,
  ErrorNote,
  Field,
  Input,
  PageHeader,
  Select,
} from '../components/ui'
import { cameraAvailable, decodeImageFile, scanFromCamera, type CameraScan } from '../lib/barcode'
import { LOCATIONS, UNITS } from '../lib/constants'

type Form = {
  ingredient_name: string
  quantity: string
  unit: string
  expiry_date: string
  location: string
  cost: string
}

const EMPTY_FORM: Form = {
  ingredient_name: '',
  quantity: '1',
  unit: 'unit',
  expiry_date: '',
  location: 'fridge',
  cost: '',
}

function formFor(product: ScanProduct): Form {
  return {
    ...EMPTY_FORM,
    // Prefer the ingredient we recognised; the product name is a brand label and
    // typing it in verbatim is what stops recipes matching the stock.
    ingredient_name: product.ingredient_name ?? product.name ?? '',
    quantity: product.quantity ? String(product.quantity) : '1',
    unit: product.unit && UNITS.includes(product.unit) ? product.unit : 'unit',
  }
}

function MatchNote({ product }: { product: ScanProduct }) {
  if (!product.found) {
    return (
      <p className="text-sm text-amber-200/80">
        Nothing known about this barcode — fill it in below and Foodie will remember it next
        time.
      </p>
    )
  }
  if (product.ingredient_name === null) {
    return (
      <p className="text-sm text-amber-200/80">
        Found the product but not a matching ingredient. Name it below and the barcode will be
        linked to it.
      </p>
    )
  }
  return (
    <p className="text-sm text-emerald-300/80">
      Matched to <span className="font-medium">{product.ingredient_name}</span>
      {product.match_method === 'remembered' ? ' (remembered from a previous scan)' : ''}
    </p>
  )
}

function CameraPane({ onCode, onClose }: { onCode: (code: string) => void; onClose: () => void }) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let scan: CameraScan | null = null
    let cancelled = false
    const video = videoRef.current
    if (!video) return

    scanFromCamera(video, onCode)
      .then((handle) => {
        if (cancelled) handle.stop()
        else scan = handle
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : 'Camera unavailable'))

    return () => {
      cancelled = true
      scan?.stop()
    }
  }, [onCode])

  return (
    <div className="mt-3 space-y-2">
      <video ref={videoRef} className="w-full rounded-lg border border-white/10 bg-black" muted />
      {error && <p className="text-sm text-rose-300">{error}</p>}
      <Button variant="ghost" onClick={onClose}>
        Stop camera
      </Button>
    </div>
  )
}

export default function Scan() {
  const lookup = useLookupBarcode()
  const addItem = useScanToInventory()
  const [barcode, setBarcode] = useState('')
  const [product, setProduct] = useState<ScanProduct | null>(null)
  const [form, setForm] = useState<Form>(EMPTY_FORM)
  const [decodeError, setDecodeError] = useState<string | null>(null)
  const [added, setAdded] = useState<string | null>(null)
  const [cameraOn, setCameraOn] = useState(false)
  const canUseCamera = cameraAvailable()

  const runLookup = (code: string) => {
    setDecodeError(null)
    setAdded(null)
    setBarcode(code)
    lookup.mutate(code, {
      onSuccess: (result) => {
        setProduct(result)
        setForm(formFor(result))
      },
    })
  }

  const onPhoto = async (file: File | undefined) => {
    if (!file) return
    setDecodeError(null)
    const code = await decodeImageFile(file)
    if (!code) {
      setDecodeError('No barcode found in that photo. Try again closer, or type the number in.')
      return
    }
    runLookup(code)
  }

  const onCameraCode = (code: string) => {
    setCameraOn(false)
    runLookup(code)
  }

  const update = (key: keyof Form, value: string) => setForm((f) => ({ ...f, [key]: value }))

  const submit = (event: React.FormEvent) => {
    event.preventDefault()
    const quantity = Number(form.quantity)
    if (!form.ingredient_name.trim() || !Number.isFinite(quantity) || quantity <= 0) return
    addItem.mutate(
      {
        barcode,
        ingredient_name: form.ingredient_name.trim(),
        quantity,
        unit: form.unit,
        expiry_date: form.expiry_date || undefined,
        location: form.location,
        cost: form.cost ? Number(form.cost) : undefined,
      },
      {
        onSuccess: (item) => {
          setAdded(item.ingredient.display_name)
          setProduct(null)
          setBarcode('')
          setForm(EMPTY_FORM)
        },
      },
    )
  }

  return (
    <>
      <PageHeader
        title="Scan"
        subtitle="Point at a barcode to add shopping to the kitchen"
      />

      {added && (
        <Card className="mb-4 border-emerald-500/30 bg-emerald-500/5">
          <p className="text-sm text-emerald-300">
            Added {added}. Scan the next one.
          </p>
        </Card>
      )}

      <Card className="mb-4">
        <div className="flex flex-wrap items-center gap-2">
          <label className="inline-flex min-h-11 cursor-pointer items-center rounded-lg bg-emerald-500 px-4 text-sm font-medium text-black hover:bg-emerald-400">
            Take a photo
            <input
              type="file"
              accept="image/*"
              capture="environment"
              className="sr-only"
              onChange={(e) => void onPhoto(e.target.files?.[0])}
            />
          </label>
          {canUseCamera && !cameraOn && (
            <Button variant="secondary" onClick={() => setCameraOn(true)}>
              Use live camera
            </Button>
          )}
        </div>

        {!canUseCamera && (
          <p className="mt-2 text-xs text-white/40">
            Live camera needs HTTPS, so photo capture is used instead. Serving Foodie over
            Tailscale HTTPS enables it.
          </p>
        )}

        {cameraOn && <CameraPane onCode={onCameraCode} onClose={() => setCameraOn(false)} />}

        <div className="mt-4 border-t border-white/10 pt-4">
          <Field label="Or type the barcode">
            <div className="flex gap-2">
              <Input
                inputMode="numeric"
                placeholder="5000112345678"
                value={barcode}
                onChange={(e) => setBarcode(e.target.value)}
              />
              <Button
                variant="secondary"
                disabled={!barcode.trim() || lookup.isPending}
                onClick={() => runLookup(barcode.trim())}
              >
                Look up
              </Button>
            </div>
          </Field>
        </div>

        {decodeError && <p className="mt-3 text-sm text-amber-200/80">{decodeError}</p>}
        {lookup.isError && <ErrorNote error={lookup.error} />}
      </Card>

      {product && (
        <Card>
          <div className="mb-3">
            <p className="font-medium text-white">{product.name ?? `Barcode ${product.barcode}`}</p>
            {product.brand && <p className="text-xs text-white/40">{product.brand}</p>}
            <div className="mt-1">
              <MatchNote product={product} />
            </div>
          </div>

          <form onSubmit={submit} className="space-y-4">
            <Field label="Item">
              <Input
                value={form.ingredient_name}
                placeholder="e.g. Milk"
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
                  step="any"
                  value={form.cost}
                  onChange={(e) => update('cost', e.target.value)}
                />
              </Field>
            </div>
            {addItem.isError && <ErrorNote error={addItem.error} />}
            <div className="flex gap-2">
              <Button type="submit" disabled={addItem.isPending}>
                Add to kitchen
              </Button>
              <Button variant="ghost" onClick={() => setProduct(null)}>
                Cancel
              </Button>
            </div>
          </form>
        </Card>
      )}
    </>
  )
}
