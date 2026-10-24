import { BarcodeFormat, BrowserMultiFormatReader, DecodeHintType } from '@zxing/library'

// Groceries are EAN/UPC. Restricting the formats makes decoding both faster and
// far less likely to "successfully" read a wrong code off packaging text.
const FORMATS = [
  BarcodeFormat.EAN_13,
  BarcodeFormat.EAN_8,
  BarcodeFormat.UPC_A,
  BarcodeFormat.UPC_E,
  BarcodeFormat.CODE_128,
]

function createReader(): BrowserMultiFormatReader {
  const hints = new Map()
  hints.set(DecodeHintType.POSSIBLE_FORMATS, FORMATS)
  hints.set(DecodeHintType.TRY_HARDER, true)
  return new BrowserMultiFormatReader(hints)
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

export async function decodeImageFile(file: File): Promise<string | null> {
  const url = URL.createObjectURL(file)
  const reader = createReader()
  try {
    const result = await reader.decodeFromImageUrl(url)
    return result.getText()
  } catch {
    // No barcode in the photo is an ordinary outcome, not an error worth throwing.
    return null
  } finally {
    reader.reset()
    URL.revokeObjectURL(url)
  }
}

export interface CameraScan {
  stop: () => void
}

export async function scanFromCamera(
  video: HTMLVideoElement,
  onResult: (code: string) => void,
): Promise<CameraScan> {
  const reader = createReader()
  await reader.decodeFromVideoDevice(null, video, (result) => {
    if (result) onResult(result.getText())
  })
  return { stop: () => reader.reset() }
}
