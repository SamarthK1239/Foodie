import { expect, test } from '@playwright/test'
import { parseMethod } from '../src/lib/method'

// Pure parser checks: no browser needed, but they live here because Playwright
// is the only test runner the frontend has.

test('splits newline-separated instructions into steps', () => {
  const blocks = parseMethod('Heat the oven to 200C.\nChop the onions.\nBake for 20 mins.')
  expect(blocks.map((b) => b.kind)).toEqual(['step', 'step', 'step'])
  expect(blocks[0].text).toBe('Heat the oven to 200C.')
})

test('strips numbering a source already carries', () => {
  const blocks = parseMethod('1. Heat the oven.\n2) Chop onions.\nSTEP 3: Bake.\nStep 4 Serve.')
  expect(blocks.map((b) => b.text)).toEqual([
    'Heat the oven.',
    'Chop onions.',
    'Bake.',
    'Serve.',
  ])
})

test('treats a short colon-terminated line as a heading without consuming a step number', () => {
  const blocks = parseMethod('For the custard:\nPour the milk in.\nSimmer gently.')
  expect(blocks[0]).toEqual({ kind: 'heading', text: 'For the custard' })
  expect(blocks.filter((b) => b.kind === 'step')).toHaveLength(2)
})

test('does not demote a "For the ..." instruction to a heading', () => {
  // Real corpora are full of steps that open this way; treating the opener as a
  // heading marker would silently drop instructions.
  const blocks = parseMethod(
    'For the custard, pour the milk into a large saucepan and bring to a simmer.\nStir well.',
  )
  expect(blocks[0].kind).toBe('step')
})

test('never splits a blob on sentence punctuation', () => {
  // "gas 7." is an oven setting, not step 7.
  const blocks = parseMethod('Heat oven to 220C/200C fan/gas 7. Rub the butter into the flour.')
  expect(blocks).toHaveLength(1)
  expect(blocks[0].kind).toBe('paragraph')
})

test('recovers steps from a blob only when numbering runs 1, 2, 3', () => {
  const numbered = parseMethod(
    '1. Heat the oven to 200C. 2. Chop the onions finely. 3. Bake for 20 minutes.',
  )
  expect(numbered.map((b) => b.kind)).toEqual(['step', 'step', 'step'])
  expect(numbered[0].text).toBe('Heat the oven to 200C.')

  const prose = parseMethod('Bake at gas 7. Rest 5 mins. Serve at 3. Enjoy it.')
  expect(prose).toHaveLength(1)
})

test('keeps any preamble that precedes step 1', () => {
  const blocks = parseMethod('Preheat everything first. 1. Heat the oven. 2. Chop the onions.')
  expect(blocks).toHaveLength(3)
  expect(blocks[0].text).toContain('Preheat')
})

test('handles empty, blank and CRLF input', () => {
  expect(parseMethod('')).toEqual([])
  expect(parseMethod('   \n  \n')).toEqual([])
  expect(parseMethod('A step here.\n\n\nAnother step.')).toHaveLength(2)
  expect(parseMethod('One step.\r\nTwo steps.')).toHaveLength(2)
})
