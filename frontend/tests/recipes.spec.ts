import { test, expect, type APIRequestContext } from '@playwright/test'

// Exercises the three recipe-page features end to end: formatted method,
// favourites, and planning a week that feeds the grocery list.

// Deliberately obscure: planning only shops for what you lack, so an ingredient
// another spec happens to seed into stock would produce no grocery row at all.
const INGREDIENTS = ['200 g gooseberry puree', '100 g damson jam']

const METHOD = [
  'Heat the oven to 200C/180C fan/gas 6.',
  'Rub the butter into the flour until it looks like breadcrumbs.',
  'Bake for 25 minutes until golden.',
].join('\n')

async function makeRecipe(request: APIRequestContext, title: string, ingredients: string[]) {
  const response = await request.post('/api/recipes', {
    data: {
      title,
      instructions: METHOD,
      servings: 2,
      tags: [],
      ingredients: ingredients.map((raw_text) => ({ raw_text, optional: false })),
    },
  })
  expect(response.ok()).toBeTruthy()
  return response.json()
}

async function reset(request: APIRequestContext) {
  const plan = await (await request.get('/api/meal-plan')).json()
  for (const entry of plan.entries) await request.delete(`/api/meal-plan/${entry.id}`)

  const recipes = await (await request.get('/api/recipes?limit=100')).json()
  for (const recipe of recipes.items) await request.delete(`/api/recipes/${recipe.id}`)

  for (const status of ['pending', 'purchased']) {
    const items = await (await request.get(`/api/grocery?status=${status}`)).json()
    for (const item of items) await request.delete(`/api/grocery/${item.id}`)
  }
}

test.beforeEach(async ({ request }) => {
  await reset(request)
})

test.afterAll(async ({ playwright, baseURL }) => {
  const request = await playwright.request.newContext({ baseURL })
  await reset(request)
  await request.dispose()
})

test('method renders as discrete numbered steps, not a wall of text', async ({ page, request }) => {
  const recipe = await makeRecipe(request, 'Shortcrust tart', INGREDIENTS)

  await page.goto(`/recipes/${recipe.id}`, { waitUntil: 'domcontentloaded' })
  const steps = page.locator('ol li')
  await expect(steps).toHaveCount(3)
  await expect(steps.first()).toContainText('Heat the oven')
  // The numbering comes from the renderer, so the oven temperature in step one
  // must not be mistaken for a step marker.
  await expect(steps.first()).toContainText('200C/180C fan/gas 6')
})

test('a recipe can be favourited and then filtered to', async ({ page, request }) => {
  await makeRecipe(request, 'Apple cake', ['2 apples'])
  await makeRecipe(request, 'Zebra cake', ['3 eggs'])

  await page.goto('/recipes', { waitUntil: 'domcontentloaded' })
  await expect(page.getByText('Zebra cake')).toBeVisible()

  const zebraCard = page.locator('a', { hasText: 'Zebra cake' })
  await zebraCard.getByRole('button', { name: 'Add to favourites' }).click()
  await expect(zebraCard.getByRole('button', { name: 'Remove from favourites' })).toBeVisible()

  // Starring must not navigate, even though the whole card is a link.
  await expect(page).toHaveURL(/\/recipes$/)

  await page.getByRole('button', { name: '★ Favourites' }).click()
  await expect(page.getByText('Zebra cake')).toBeVisible()
  await expect(page.getByText('Apple cake')).toHaveCount(0)
})

test('favourites-first sorting floats starred recipes above alphabetical order', async ({
  page,
  request,
}) => {
  await makeRecipe(request, 'Apple cake', ['2 apples'])
  const zebra = await makeRecipe(request, 'Zebra cake', ['3 eggs'])
  await request.post(`/api/recipes/${zebra.id}/favorite`, { data: { is_favorite: true } })

  await page.goto('/recipes', { waitUntil: 'domcontentloaded' })
  await expect(page.locator('a p.font-medium').first()).toHaveText('Apple cake')

  await page.getByRole('combobox').selectOption('favorite')
  await expect(page.locator('a p.font-medium').first()).toHaveText('Zebra cake')
})

test('planning a recipe for the week fills the grocery list', async ({ page, request }) => {
  const recipe = await makeRecipe(request, 'Shortcrust tart', INGREDIENTS)

  await page.goto(`/recipes/${recipe.id}`, { waitUntil: 'domcontentloaded' })
  await page.getByRole('button', { name: 'Add to this week' }).click()
  await expect(page.getByRole('button', { name: '✓ Planned this week' })).toBeVisible()

  await page.goto('/grocery', { waitUntil: 'domcontentloaded' })
  await expect(page.getByRole('heading', { name: 'Planned this week' })).toBeVisible()
  const list = page.locator('p.text-sm.font-medium')
  await expect(list.filter({ hasText: 'Gooseberry puree' })).toHaveCount(1)
  await expect(list.filter({ hasText: 'Damson jam' })).toHaveCount(1)

  // Unplanning withdraws exactly what planning added.
  await page.goto(`/recipes/${recipe.id}`, { waitUntil: 'domcontentloaded' })
  await page.getByRole('button', { name: '✓ Planned this week' }).click()
  await expect(page.getByRole('button', { name: 'Add to this week' })).toBeVisible()

  await page.goto('/grocery', { waitUntil: 'domcontentloaded' })
  await expect(page.getByRole('heading', { name: 'Planned this week' })).toHaveCount(0)
  await expect(page.locator('p.text-sm.font-medium').filter({ hasText: 'Gooseberry puree' })).toHaveCount(
    0,
  )
})

test('the recipe detail toolbar stays on one row at desktop width', async ({ page, request }) => {
  const recipe = await makeRecipe(request, 'Toolbar check', INGREDIENTS)
  await page.setViewportSize({ width: 1100, height: 900 })
  await page.goto(`/recipes/${recipe.id}`, { waitUntil: 'domcontentloaded' })

  // The shared Input hardcodes a width, and Tailwind resolves a duplicated
  // width utility by stylesheet order rather than by the order classes are
  // listed, so a plain `w-20` override loses to it. The batch multiplier then
  // spans the header and shunts the action buttons onto their own rows.
  const multiplier = page.locator('input[type=number][title="Batch multiplier"]')
  const deleteButton = page.getByRole('button', { name: 'Delete' })
  await expect(multiplier).toBeVisible()

  const mBox = (await multiplier.boundingBox())!
  const dBox = (await deleteButton.boundingBox())!
  expect(mBox.width).toBeLessThan(120)
  expect(Math.abs(mBox.y - dBox.y)).toBeLessThan(mBox.height)
})
