/** Canonical plain-object guard for this package. Narrows only to an object; fields stay `unknown`. */
export function isRecord(x: unknown): x is Record<string, unknown> {
  return typeof x === 'object' && x !== null && !Array.isArray(x)
}

export function isNumberArray(x: unknown): x is number[] {
  return Array.isArray(x) && x.every((v) => typeof v === 'number' || v === null)
}
