import { test, expect, type Page } from '@playwright/test'

// A real EAN-13 (check digit 4 computed over 500011234567).
const CODE = '5000112345674'

// iPhone still sizes: the default 12MP frame, and the 48MP frame the Pro models
// shoot. The 48MP case is the one that used to come back blank, because its
// 48.8M pixels are roughly three times iOS Safari's canvas area cap.
const IPHONE_12MP = { width: 4032, height: 3024 }
const IPHONE_48MP = { width: 8064, height: 6048 }

/**
 * Draws a genuine EAN-13 into a photo-sized JPEG using the browser as the
 * encoder. Decoding a synthetic-but-valid barcode is the only way to assert the
 * photo path end to end without a physical phone.
 */
async function barcodePhoto(
  page: Page,
  size: { width: number; height: number },
): Promise<Buffer> {
  const dataUrl = await page.evaluate(
    ({ code, width, height }) => {
      const L = [
        '0001101', '0011001', '0010011', '0111101', '0100011',
        '0110001', '0101111', '0111011', '0110111', '0001011',
      ]
      const G = [
        '0100111', '0110011', '0011011', '0100001', '0011101',
        '0111001', '0000101', '0010001', '0001001', '0010111',
      ]
      const R = [
        '1110010', '1100110', '1101100', '1000010', '1011100',
        '1001110', '1010000', '1000100', '1001000', '1110100',
      ]
      const PARITY = [
        'LLLLLL', 'LLGLGG', 'LLGGLG', 'LLGGGL', 'LGLLGG',
        'LGGLLG', 'LGGGLL', 'LGLGLG', 'LGLGGL', 'LGGLGL',
      ]

      const d = code.split('').map(Number)
      const parity = PARITY[d[0]]
      let bits = '101'
      for (let i = 1; i <= 6; i++) bits += (parity[i - 1] === 'L' ? L : G)[d[i]]
      bits += '01010'
      for (let i = 7; i <= 12; i++) bits += R[d[i]]
      bits += '101'

      const canvas = document.createElement('canvas')
      canvas.width = width
      canvas.height = height
      const ctx = canvas.getContext('2d')!
      ctx.fillStyle = '#fff'
      ctx.fillRect(0, 0, width, height)

      // Span about a third of the frame, which is how a barcode lands when you
      // hold a packet at arm's length rather than filling the viewfinder.
      const moduleW = Math.floor(width / 3 / bits.length)
      const barH = moduleW * 70
      const x0 = Math.round((width - moduleW * bits.length) / 2)
      const y0 = Math.round((height - barH) / 2)

      ctx.fillStyle = '#000'
      for (let i = 0; i < bits.length; i++) {
        if (bits[i] === '1') ctx.fillRect(x0 + i * moduleW, y0, moduleW, barH)
      }
      return canvas.toDataURL('image/jpeg', 0.9)
    },
    { code: CODE, ...size },
  )
  return Buffer.from(dataUrl.split(',')[1], 'base64')
}

for (const [label, size] of [
  ['12MP', IPHONE_12MP],
  ['48MP', IPHONE_48MP],
] as const) {
  test(`decodes a ${label} phone photo and looks the barcode up`, async ({ page }) => {    let requested: string | null = null
    await page.route('**/api/scan/barcode/**', async (route) => {
      requested = decodeURIComponent(new URL(route.request().url()).pathname.split('/').pop()!)
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          found: true,
          barcode: requested,
          name: 'Semi Skimmed Milk',
          ingredient_name: 'Milk',
          match_method: 'fuzzy',
          quantity: 2,
          unit: 'l',
        }),
      })
    })

    await page.goto('/scan')
    const photo = await barcodePhoto(page, size)

    const started = Date.now()
    await page.locator('input[type=file][capture]').first().setInputFiles({
      name: 'IMG_0001.jpg',
      mimeType: 'image/jpeg',
      buffer: photo,
    })

    await expect(page.getByText('Matched to')).toBeVisible({ timeout: 20_000 })
    const elapsed = Date.now() - started

    expect(requested).toBe(CODE)
    // The bug was a ~30s main-thread stall. Anything near that is a regression,
    // and a generous ceiling keeps this honest on slow CI without going vacuous.
    expect(elapsed).toBeLessThan(10_000)
  })
}

/** A photo with no barcode in it: the path that used to exhaust TRY_HARDER. */
async function noisyPhoto(
  page: Page,
  size: { width: number; height: number },
): Promise<Buffer> {
  const dataUrl = await page.evaluate(
    ({ width, height }) => {
      const canvas = document.createElement('canvas')
      canvas.width = width
      canvas.height = height
      const ctx = canvas.getContext('2d')!
      const band = ctx.createImageData(width, Math.min(height, 512))
      for (let i = 0; i < band.data.length; i += 4) {
        const v = (Math.random() * 255) | 0
        band.data[i] = band.data[i + 1] = band.data[i + 2] = v
        band.data[i + 3] = 255
      }
      for (let y = 0; y < height; y += 512) ctx.putImageData(band, 0, y)
      return canvas.toDataURL('image/jpeg', 0.9)
    },
    size,
  )
  return Buffer.from(dataUrl.split(',')[1], 'base64')
}

test('reports no barcode instead of hanging on a 48MP photo without one', async ({ page }) => {
  await page.goto('/scan')
  const photo = await noisyPhoto(page, IPHONE_48MP)

  await page.locator('input[type=file][capture]').first().setInputFiles({
    name: 'IMG_0002.jpg',
    mimeType: 'image/jpeg',
    buffer: photo,
  })

  // The decode is budgeted, so this has to resolve rather than run to exhaustion.
  await expect(page.getByText('No barcode found')).toBeVisible({ timeout: 30_000 })
})

test('shows progress while a slow photo decodes', async ({ page }) => {
  await page.goto('/scan')
  const photo = await noisyPhoto(page, IPHONE_48MP)

  await page.locator('input[type=file][capture]').first().setInputFiles({
    name: 'IMG_0003.jpg',
    mimeType: 'image/jpeg',
    buffer: photo,
  })

  // Painting this at all requires the decode to yield the main thread, which is
  // what stops iOS rendering the page as a black rectangle mid-decode.
  await expect(page.getByText('Reading photo…')).toBeVisible({ timeout: 15_000 })
})
