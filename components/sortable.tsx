"use client"
import { useMemo, useState } from "react"
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react"

export type SortDir = "asc" | "desc"
export type SortState = { key: string; dir: SortDir } | null
type Accessor<T> = (row: T) => string | number | null | undefined

/** Click cycle: default direction -> opposite direction -> cleared. */
export function nextSort(
  current: SortState,
  key: string,
  defaultDir: SortDir = "asc"
): SortState {
  if (!current || current.key !== key) return { key, dir: defaultDir }
  if (current.dir === defaultDir) {
    return { key, dir: defaultDir === "asc" ? "desc" : "asc" }
  }
  return null
}

export function sortRows<T>(
  rows: T[],
  sort: SortState,
  accessors: Record<string, Accessor<T>>
): T[] {
  if (!sort) return rows
  const get = accessors[sort.key]
  if (!get) return rows
  const mult = sort.dir === "asc" ? 1 : -1
  return [...rows].sort((a, b) => {
    const av = get(a)
    const bv = get(b)
    const aNull = av == null || av === ""
    const bNull = bv == null || bv === ""
    if (aNull && bNull) return 0
    if (aNull) return 1 // empty values always sink to the bottom
    if (bNull) return -1
    if (typeof av === "number" && typeof bv === "number") return (av - bv) * mult
    return (
      String(av).localeCompare(String(bv), undefined, {
        numeric: true,
        sensitivity: "base",
      }) * mult
    )
  })
}

/** Client-side sorting for lists that already hold all of their rows. */
export function useSort<T>(
  rows: T[],
  accessors: Record<string, Accessor<T>>,
  initial: SortState = null
) {
  const [sort, setSort] = useState<SortState>(initial)
  const sorted = useMemo(
    () => sortRows(rows, sort, accessors),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [rows, sort]
  )
  return { sorted, sort, setSort }
}

export function SortableTh({
  label,
  sortKey,
  sort,
  onSort,
  defaultDir = "asc",
  align = "left",
  className = "px-4 py-3",
  children,
}: {
  label: string
  sortKey: string
  sort: SortState
  onSort: (next: SortState) => void
  defaultDir?: SortDir
  align?: "left" | "right"
  className?: string
  children?: React.ReactNode
}) {
  const active = sort?.key === sortKey
  const Icon = !active ? ArrowUpDown : sort!.dir === "asc" ? ArrowUp : ArrowDown
  return (
    <th
      className={`${className} ${align === "right" ? "text-right" : ""}`}
      aria-sort={
        active ? (sort!.dir === "asc" ? "ascending" : "descending") : "none"
      }
    >
      <span
        className={`inline-flex items-center gap-1 ${
          align === "right" ? "flex-row-reverse" : ""
        }`}
      >
        <button
          type="button"
          onClick={() => onSort(nextSort(sort, sortKey, defaultDir))}
          className={`inline-flex items-center gap-1 uppercase tracking-wider transition hover:text-navy ${
            active ? "text-navy" : ""
          }`}
          title={`Sort by ${label.toLowerCase()}`}
        >
          {label}
          <Icon className={`h-3 w-3 ${active ? "opacity-100" : "opacity-40"}`} />
        </button>
        {children}
      </span>
    </th>
  )
}
