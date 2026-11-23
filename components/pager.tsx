"use client"
import { useEffect, useState } from "react"

export const PAGE_SIZE_OPTIONS = [25, 50, 100]

export type PagerState = {
  page: number
  pageSize: number
  total: number
  totalPages: number
  from: number
  to: number
  setPage: (p: number) => void
  setPageSize: (n: number) => void
}

/** Client-side paging for lists that already hold all of their rows. Call it on the already-sorted rows. */
export function usePager<T>(rows: T[], resetKey = "", initialSize = 50) {
  const [page, setPage] = useState(1)
  const [pageSize, setPageSizeState] = useState(initialSize)
  const total = rows.length
  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  // Back to page 1 when the sort changes or the data changes
  useEffect(() => {
    setPage(1)
  }, [resetKey, total])

  const current = Math.min(page, totalPages)
  const start = (current - 1) * pageSize
  const pager: PagerState = {
    page: current,
    pageSize,
    total,
    totalPages,
    from: total === 0 ? 0 : start + 1,
    to: Math.min(start + pageSize, total),
    setPage,
    setPageSize: (n) => {
      setPageSizeState(n)
      setPage(1)
    },
  }
  return { pageRows: rows.slice(start, start + pageSize), pager }
}

function pageRange(current: number, total: number): (number | "...")[] {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1)
  const pages: (number | "...")[] = []
  const add = (p: number) => {
    if (!pages.includes(p)) pages.push(p)
  }
  add(1)
  if (current > 3) pages.push("...")
  for (let p = Math.max(2, current - 1); p <= Math.min(total - 1, current + 1); p++) add(p)
  if (current < total - 2) pages.push("...")
  add(total)
  return pages
}

/** "Showing 1–50 of 312 items" plus the Per page: 25 50 100 selector. */
export function PagerBar({ pager, noun = "items" }: { pager: PagerState; noun?: string }) {
  if (pager.total === 0) return null
  return (
    <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
      <p className="text-sm text-muted-foreground">
        Showing <span className="font-medium text-foreground">{pager.from}–{pager.to}</span> of{" "}
        <span className="font-medium text-foreground">{pager.total.toLocaleString()}</span> {noun}
      </p>
      <div className="flex items-center gap-2 text-sm">
        <span className="text-muted-foreground">Per page:</span>
        {PAGE_SIZE_OPTIONS.map((size) => (
          <button
            key={size}
            onClick={() => pager.setPageSize(size)}
            className={`rounded px-2.5 py-1 font-medium transition ${
              pager.pageSize === size ? "bg-navy text-white" : "text-muted-foreground hover:text-navy"
            }`}
          >
            {size}
          </button>
        ))}
      </div>
    </div>
  )
}

/** Previous / page numbers / Next. Hidden when there is only one page. */
export function PagerNav({ pager }: { pager: PagerState }) {
  if (pager.totalPages <= 1) return null
  return (
    <div className="mt-6 flex items-center justify-between">
      <button
        onClick={() => pager.setPage(Math.max(1, pager.page - 1))}
        disabled={pager.page <= 1}
        className="rounded-lg border border-border px-4 py-2 text-sm font-medium text-navy transition hover:bg-muted disabled:cursor-not-allowed disabled:opacity-40"
      >
        Previous
      </button>
      <div className="flex items-center gap-1">
        {pageRange(pager.page, pager.totalPages).map((p, i) =>
          p === "..." ? (
            <span key={`e-${i}`} className="px-2 text-muted-foreground">...</span>
          ) : (
            <button
              key={p}
              onClick={() => pager.setPage(p)}
              className={`min-w-[36px] rounded px-2 py-1 text-sm font-medium transition ${
                p === pager.page ? "bg-navy text-white" : "text-muted-foreground hover:text-navy"
              }`}
            >
              {p}
            </button>
          )
        )}
      </div>
      <button
        onClick={() => pager.setPage(Math.min(pager.totalPages, pager.page + 1))}
        disabled={pager.page >= pager.totalPages}
        className="rounded-lg border border-border px-4 py-2 text-sm font-medium text-navy transition hover:bg-muted disabled:cursor-not-allowed disabled:opacity-40"
      >
        Next
      </button>
    </div>
  )
}
