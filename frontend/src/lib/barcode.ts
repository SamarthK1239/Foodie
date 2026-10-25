import {
  BarcodeFormat,
  BinaryBitmap,
  BrowserMultiFormatReader,
  DecodeHintType,
  HybridBinarizer,
  MultiFormatReader,
  RGBLuminanceSource,
} from '@zxing/library'

// Groceries are EAN/UPC. Restricting the formats makes decoding both faster and
// far less likely to "successfully" read a wrong code off packaging text.
const FORMATS = [
  BarcodeFormat.EAN_13,
  BarcodeFormat.EAN_8,
  BarcodeFormat.UPC_A,
  BarcodeFormat.UPC_E,
  BarcodeFormat.CODE_128,
]

function decodeHints(): Map<DecodeHintType, unknown> {
  const hints = new Map<DecodeHintType, unknown>()
  hints.set(DecodeHintType.POSSIBLE_FORMATS, FORMATS)
  hints.set(DecodeHintType.TRY_HARDER, true)
  return hints
}

/**
 * Live camera needs getUserMedia, which browsers refuse over plain HTTP on any
 * origin but localhost. Behind Tailscale without HTTPS that means photo capture
 * is the only option, so detect it rather than offering a button that fails.
 */
export function cameraAvailable(): boolean {
  return (
    typeof window !== 'undefined' &&
    window.isSecureContext &&
    typeof navigator !== 'undefined' &&
    !!navigator.mediaDevices?.getUserMedia
  )
}

/**
 * Longest edge we are willing to decode. An EAN-13 is 95 modules wide, so even a
 * barcode spanning a sixth of a 1600px frame still gets ~2.8px per module, which
 * is comfortably above the ~2px the binarizer needs.
 */
const MAX_EDGE_PX = 1600

export class BlankImageError extends Error {
  constructor() {
    super('The photo came back blank.')
    this.name = 'BlankImageError'
  }
}

interface Pass {
  maxEdge: number
  /** Fraction of the source to keep, centred. 1 means the whole frame. */
  crop: number
  /** Quarter turns applied before decoding. */
  rotate: 0 | 1
}

/**
 * Ordered cheapest-and-most-likely first. A centred crop is tried because
 * downscaling the whole frame is what destroys a small, distant barcode, and a
 * quarter turn is tried because RGBLuminanceSource cannot rotate itself, so
 * ZXing's own TRY_HARDER rotation pass never runs for us.
 */
const PASSES: Pass[] = [
  { maxEdge: 1024, crop: 1, rotate: 0 },
  { maxEdge: MAX_EDGE_PX, crop: 1, rotate: 0 },
  { maxEdge: MAX_EDGE_PX, crop: 0.6, rotate: 0 },
  { maxEdge: MAX_EDGE_PX, crop: 1, rotate: 1 },
  { maxEdge: MAX_EDGE_PX, crop: 0.6, rotate: 1 },
]

/**
 * Wall-clock budget for the whole decode. A fixed pass list is the wrong shape
 * here: the same five passes that cost ~3s on a laptop cost far more on a phone,
 * and the original bug was precisely an unbounded decode. Budgeting instead of
 * counting keeps the worst case roughly constant across devices, at the cost of
 * trying fewer renderings on slow hardware.
 */
const BUDGET_MS = 3000

async function loadImage(file: File): Promise<HTMLImageElement> {
  const url = URL.createObjectURL(file)
  const img = new Image()
  try {
    img.src = url
    // decode() surfaces a corrupt or unsupported file as a rejection instead of
    // leaving us polling an image that never completes.
    await img.decode()
    return img
  } finally {
    // The element keeps the decoded bitmap alive, so releasing the URL here is
    // safe and avoids leaking a multi-megabyte blob per photo.
    URL.revokeObjectURL(url)
  }
}

interface GrayImage {
  data: Uint8ClampedArray
  width: number
  height: number
  blank: boolean
}

/**
 * Draws the source into a small canvas. Scaling happens inside drawImage, so we
 * never allocate a canvas at the photo's native size — which is the whole point:
 * iOS Safari caps canvas area (~16.7M px) and silently hands back a blank
 * surface above it, and a 48MP iPhone photo is roughly three times that.
 */
function renderScaled(
  img: HTMLImageElement,
  crop: number,
  maxEdge: number,
): HTMLCanvasElement {
  const sw = Math.round(img.naturalWidth * crop)
  const sh = Math.round(img.naturalHeight * crop)
  const sx = Math.round((img.naturalWidth - sw) / 2)
  const sy = Math.round((img.naturalHeight - sh) / 2)

  const scale = Math.min(1, maxEdge / Math.max(sw, sh))
  const canvas = document.createElement('canvas')
  canvas.width = Math.max(1, Math.round(sw * scale))
  canvas.height = Math.max(1, Math.round(sh * scale))

  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('Could not read the photo.')
  ctx.drawImage(img, sx, sy, sw, sh, 0, 0, canvas.width, canvas.height)
  return canvas
}

/**
 * Grayscale pixels for one pass, derived from an already-downscaled base. Going
 * back to the full-resolution photo for every pass is what made a 48MP frame
 * cost seconds: the expensive draw is the one that reads the original.
 */
function toGray(base: HTMLCanvasElement, maxEdge: number, rotate: 0 | 1): GrayImage {
  const scale = Math.min(1, maxEdge / Math.max(base.width, base.height))
  const dw = Math.max(1, Math.round(base.width * scale))
  const dh = Math.max(1, Math.round(base.height * scale))

  const turned = rotate === 1
  const canvas = document.createElement('canvas')
  canvas.width = turned ? dh : dw
  canvas.height = turned ? dw : dh

  const ctx = canvas.getContext('2d', { willReadFrequently: true })
  if (!ctx) throw new Error('Could not read the photo.')
  if (turned) {
    ctx.translate(dh, 0)
    ctx.rotate(Math.PI / 2)
  }
  ctx.drawImage(base, 0, 0, base.width, base.height, 0, 0, dw, dh)

  const { data: rgba } = ctx.getImageData(0, 0, canvas.width, canvas.height)
  const size = canvas.width * canvas.height
  const gray = new Uint8ClampedArray(size)
  let min = 255
  let max = 0
  for (let i = 0; i < size; i++) {
    const o = i * 4
    // Green-favouring average, matching ZXing's own RGB conversion.
    const value = (rgba[o] + 2 * rgba[o + 1] + rgba[o + 2]) / 4
    gray[i] = value
    if (value < min) min = value
    if (value > max) max = value
  }

  // A uniform surface means the draw produced nothing, not that the kitchen is
  // dark. Worth distinguishing: "no barcode found" would send the user off to
  // retake a photo that was never going to work.
  return { data: gray, width: canvas.width, height: canvas.height, blank: min === max }
}

function decodeGray(gray: GrayImage, reader: MultiFormatReader): string | null {
  const source = new RGBLuminanceSource(gray.data, gray.width, gray.height)
  const bitmap = new BinaryBitmap(new HybridBinarizer(source))
  try {
    return reader.decode(bitmap, decodeHints() as Map<DecodeHintType, never>).getText()
  } catch {
    // NotFound/Checksum/Format all mean "not in this rendering", which is the
    // normal outcome for every pass but the lucky one.
    return null
  } finally {
    reader.reset()
  }
}

/** Lets the browser paint between passes so the page never looks frozen. */
function yieldToBrowser(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0))
}

/**
 * Returns the barcode, or null when the photo genuinely has none.
 * Throws BlankImageError when the browser could not give us pixels at all.
 */
export async function decodeImageFile(file: File): Promise<string | null> {
  const img = await loadImage(file)
  const reader = new MultiFormatReader()
  const deadline = Date.now() + BUDGET_MS
  // At most two reads of the full-resolution photo, memoised by crop factor.
  const bases = new Map<number, HTMLCanvasElement>()
  const baseFor = (crop: number) => {
    let base = bases.get(crop)
    if (!base) {
      base = renderScaled(img, crop, MAX_EDGE_PX)
      bases.set(crop, base)
    }
    return base
  }

  let sawPixels = false

  for (const [index, pass] of PASSES.entries()) {
    // Always run the first pass, so a slow device still gets one honest attempt.
    if (index > 0 && Date.now() > deadline) break

    const gray = toGray(baseFor(pass.crop), pass.maxEdge, pass.rotate)
    if (gray.blank) continue
    sawPixels = true

    const code = decodeGray(gray, reader)
    if (code) return code
    await yieldToBrowser()
  }

  if (!sawPixels) throw new BlankImageError()
  return null
}

export interface CameraScan {
  stop: () => void
}

export async function scanFromCamera(
  video: HTMLVideoElement,
  onResult: (code: string) => void,
): Promise<CameraScan> {
  const reader = new BrowserMultiFormatReader(decodeHints() as Map<DecodeHintType, never>)
  // Passing null as the device id makes ZXing request facingMode 'environment',
  // which is the rear camera the user is pointing at the packaging.
  await reader.decodeFromVideoDevice(null, video, (result) => {
    if (result) onResult(result.getText())
  })
  return { stop: () => reader.reset() }
}
