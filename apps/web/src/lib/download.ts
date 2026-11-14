/** Save `content` as a file via a temporary object URL (client-side; data already fetched from the API). */
export function downloadText(filename: string, content: string, type = 'application/json') {
  const url = URL.createObjectURL(new Blob([content], { type }))
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export function downloadJson(filename: string, data: unknown) {
  downloadText(filename, `${JSON.stringify(data, null, 2)}\n`)
}
