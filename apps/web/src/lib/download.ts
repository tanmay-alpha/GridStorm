/** Save `blob` as a file via a temporary object URL; the bytes are written unchanged. */
export function downloadBlob(filename: string, blob: Blob) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

/** Save `content` as a file (client-side; data already fetched from the API). */
export function downloadText(filename: string, content: string, type = 'application/json') {
  downloadBlob(filename, new Blob([content], { type }))
}

export function downloadJson(filename: string, data: unknown) {
  downloadText(filename, `${JSON.stringify(data, null, 2)}\n`)
}
