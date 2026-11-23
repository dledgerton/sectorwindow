// Shared CSV helpers for the export routes.

export function escapeCSV(val: unknown): string {
  if (val == null) return ''
  let str = String(val)
  // Stop spreadsheet apps from treating text such as an org name as a formula
  if (typeof val === 'string' && /^[=+@\t\r]/.test(str)) str = `'${str}`
  if (str.includes(',') || str.includes('"') || str.includes('\n') || str.includes('\r')) {
    return `"${str.replace(/"/g, '""')}"`
  }
  return str
}

export function toCSV(rows: Record<string, unknown>[]): string {
  const headers = Object.keys(rows[0])
  return [headers.join(','), ...rows.map(r => Object.values(r).map(escapeCSV).join(','))].join('\n')
}
