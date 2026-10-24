import { test, expect, type Page, type APIRequestContext } from '@playwright/test'

const ROUTES = ['/', '/suggestions', '/recipes', '/grocery', '/analytics', '/admin']

// Apple and Android both publish ~44px as the minimum comfortable touch target.
const MIN_TOUCH = 44

async function seed(request: APIRequestContext) {
  const today = new Date()
  const plus = (days: number) =>
    new Date(today.getTime() + days * 86_400_000).toISOString().slice(0, 10)

  // Spread across expiry buckets so the dashboard renders chips and stepper rows.
  const items = [
    { ingredient_name: 'Eggs', quantity: 6, unit: 'unit', expiry_date: plus(2) },
    { ingredient_name: 'Milk', quantity: 500, unit: 'ml', expiry_date: plus(-1) },
    { ingredient_name: 'Plain flour', quantity: 1000, unit: 'g', expiry_date: plus(120) },
    { ingredient_name: 'Butter', quantity: 250, unit: 'g' },
  ]
  for (const item of items) {
    await request.post('/api/inventory/items', { data: item })
  }

  await request.post('/api/grocery', {
    data: { label: 'Olive oil', ingredient_name: 'Olive oil', quantity: 1, unit: 'unit' },
  })

  await request.post('/api/recipes', {
    data: {
      title: 'Test pancakes with a deliberately long title to stress the layout',
      instructions: 'Mix everything, then fry.',
      servings: 4,
      total_minutes: 20,
      ingredients: [
        { name: 'Eggs', quantity: 2, unit: 'unit' },
        { name: 'Milk', quantity: 300, unit: 'ml' },
        { name: 'Plain flour', quantity: 200, unit: 'g' },
      ],
    },
  })
}

async function settle(page: Page, route: string) {
  // networkidle never fires here because react-query polls in the background.
  await page.goto(route, { waitUntil: 'domcontentloaded' })
  await expect(page.locator('main')).toBeVisible()
  await page.waitForTimeout(1200)
}

test.beforeAll(async ({ playwright, baseURL }) => {
  const request = await playwright.request.newContext({ baseURL })
  await seed(request)
  await request.dispose()
})

test.describe('mobile layout', () => {
  for (const route of ROUTES) {
    test(`${route} has no horizontal overflow`, async ({ page }) => {
      await settle(page, route)
      const overflow = await page.evaluate(() => {
        const de = document.documentElement
        return de.scrollWidth - de.clientWidth
      })
      expect(overflow, `${route} overflows horizontally by ${overflow}px`).toBe(0)
    })

    test(`${route} has adequate touch targets`, async ({ page }) => {
      await settle(page, route)
      const undersized = await page.evaluate((min) => {
        const nodes = [
          ...document.querySelectorAll(
            'button, input, select, textarea, a[class*="inline-flex"], nav a',
          ),
        ]
        return nodes
          .filter((node) => {
            const box = node.getBoundingClientRect()
            if (box.width === 0 || box.height === 0) return false
            if (node instanceof HTMLInputElement && node.type === 'hidden') return false
            // Checkboxes and radios stay visually small, so a wrapping label provides
            // the tap area. Other controls must meet the minimum themselves.
            const isTick =
              node instanceof HTMLInputElement &&
              (node.type === 'checkbox' || node.type === 'radio')
            const label = isTick ? node.closest('label') : null
            const hit = label ? label.getBoundingClientRect() : box
            return hit.height < min || hit.width < min
          })
          .map((node) => {
            const box = node.getBoundingClientRect()
            const label = (node.textContent || node.getAttribute('aria-label') || '').trim()
            return `${node.tagName}"${label.slice(0, 20)}" ${Math.round(box.width)}x${Math.round(box.height)}`
          })
      }, MIN_TOUCH)
      expect(undersized, `${route} has controls below ${MIN_TOUCH}px`).toEqual([])
    })
  }
})

test('every destination is reachable on a phone', async ({ page }) => {
  await settle(page, '/')

  // The four bottom-tab destinations must be tappable without opening a menu.
  for (const name of ['Kitchen', 'Cook', 'Grocery', 'Stats']) {
    await expect(page.locator('nav').last().getByRole('link', { name })).toBeVisible()
  }

  // Everything else has to be reachable through the menu.
  await page.getByRole('button', { name: 'Menu' }).click()
  for (const name of ['Dashboard', 'Recipes', 'Analytics', 'Admin']) {
    await expect(page.getByRole('link', { name, exact: true })).toBeVisible()
  }

  await page.getByRole('link', { name: 'Admin', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Admin' })).toBeVisible()

  // Navigating must dismiss the menu.
  await expect(page.getByRole('link', { name: 'Analytics', exact: true })).toBeHidden()
})

test('desktop keeps the inline nav and hides the mobile chrome', async ({ browser, baseURL }) => {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } })
  const page = await context.newPage()
  await page.goto(`${baseURL}/`, { waitUntil: 'domcontentloaded' })
  await expect(page.locator('main')).toBeVisible()

  // All six links sit inline in the header, so no menu button is needed.
  for (const name of ['Dashboard', 'Cook', 'Recipes', 'Grocery', 'Analytics', 'Admin']) {
    await expect(page.locator('header').getByRole('link', { name, exact: true })).toBeVisible()
  }
  await expect(page.getByRole('button', { name: 'Menu' })).toBeHidden()
  await expect(page.getByRole('link', { name: 'Kitchen', exact: true })).toBeHidden()

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  expect(overflow).toBe(0)
  await context.close()
})
