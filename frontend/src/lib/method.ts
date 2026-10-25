/**
 * Recipe method text arrives as newline-separated steps, which rendered into a
 * single paragraph reads as an undifferentiated block. Splitting it into
 * discrete steps is almost all of the formatting work.
 */

export type MethodBlock =
  | { kind: 'step'; text: string }
  | { kind: 'heading'; text: string }
  | { kind: 'paragraph'; text: string }

/**
 * Markers a source may already carry: "1.", "2)", "Step 3", "STEP 4:".
 * Stripped so a line never renders as "1. 1. Heat the oven".
 */
const LEADING_MARKER = /^\s*(?:step\s*)?\d{1,2}\s*[.):]\s+|^\s*step\s+\d{1,2}\s+/i

/**
 * A heading is only recognised when it is short *and* ends in a colon.
 * Keying off openers like "For the" alone would be wrong: real corpora are full
 * of steps that begin "For the custard, pour the milk into a large saucepan…",
 * and demoting those to headings would silently drop instructions.
 */
const MAX_HEADING_CHARS = 60

function isHeading(line: string): boolean {
  return line.endsWith(':') && line.length <= MAX_HEADING_CHARS
}

/**
 * Splits a single unbroken blob on embedded "1." / "Step 2" markers.
 *
 * Numbers followed by a full stop are not rare in prose — "Heat oven to
 * 220C/200C fan/gas 7. Rub the butter in" would otherwise split mid-sentence.
 * So candidates only count as step markers when they form a run starting at 1
 * and ascending by one; a stray oven setting cannot fake that.
 */
function splitOnMarkers(text: string): string[] {
  const marker = /(?:^|\s)(?:step\s*)?(\d{1,2})\s*[.)]\s+(?=[A-Z])/gi
  const found: { index: number; end: number; value: number }[] = []
  for (const match of text.matchAll(marker)) {
    found.push({
      index: match.index + (match[0].length - match[0].trimStart().length),
      end: match.index + match[0].length,
      value: Number(match[1]),
    })
  }

  const sequential = found.filter((_, i) => found[i].value === i + 1)
  if (sequential.length !== found.length || found.length < 2) return [text]

  // Anything before "1." is a preamble, not a step; keep it rather than
  // silently dropping it on the floor.
  const preamble = text.slice(0, found[0].index).trim()
  const steps = found.map((m, i) =>
    text.slice(m.end, i + 1 < found.length ? found[i + 1].index : undefined).trim(),
  )
  return [preamble, ...steps].filter(Boolean)
}

export function parseMethod(instructions: string): MethodBlock[] {
  const text = (instructions ?? '').replace(/\r\n?/g, '\n').trim()
  if (!text) return []

  let lines = text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)

  // One unbroken blob: recover steps from numbering if it is there, but do not
  // invent them by splitting on sentences. "Heat oven to 220C/200C fan/gas 7."
  // alone shows why punctuation is not a reliable step boundary.
  if (lines.length === 1) {
    const recovered = splitOnMarkers(lines[0])
    if (recovered.length < 2) return [{ kind: 'paragraph', text: lines[0] }]
    lines = recovered
  }

  return lines.map((line) => {
    if (isHeading(line)) return { kind: 'heading', text: line.replace(/:$/, '') }
    return { kind: 'step', text: line.replace(LEADING_MARKER, '').trim() }
  })
}
