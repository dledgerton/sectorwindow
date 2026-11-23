"use client"
import { useEffect, useState } from "react"
import Link from "next/link"
import { Nav } from "@/components/nav"
import { ScoreBadge } from "@/components/score-badge"
import { SortableTh, useSort } from "@/components/sortable"
import { PagerBar, PagerNav, usePager } from "@/components/pager"

interface SavedSearch {
  id: string
  name: string
  route: string
  params: Record<string, string>
  lastCount: number | null
  lastRun: string | null
  savedAt: string
}

interface SavedOrg {
  ein: string
  name: string
  city: string
  state: string
  tier: string | null
  score: number | null
  savedAt: string
}

function formatDate(iso: string | null) {
  if (!iso) return "--"
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })
}

function routeLabel(route: string) {
  const map: Record<string, string> = {
    "/": "Market Scan",
    "/hot-list": "Hot List",
    "/sector-pulse": "Sector Pulse",
  }
  return map[route] ?? route
}

function buildSearchUrl(route: string, params: Record<string, string>) {
  const qs = new URLSearchParams(params).toString()
  return qs ? `${route}?${qs}` : route
}

export default function DashboardPage() {
  const [searches, setSearches] = useState<SavedSearch[]>([])
  const [orgs, setOrgs] = useState<SavedOrg[]>([])
  const [loadingSearches, setLoadingSearches] = useState(true)
  const [loadingOrgs, setLoadingOrgs] = useState(true)
  const [deletingSearchId, setDeletingSearchId] = useState<string | null>(null)
  const [deletingOrgEin, setDeletingOrgEin] = useState<string | null>(null)
  const time = (v: string | null | undefined) => {
    const t = v ? Date.parse(v) : NaN
    return Number.isNaN(t) ? null : t
  }
  const searchSort = useSort(searches, {
    name: (r) => r.name,
    view: (r) => routeLabel(r.route),
    count: (r) => r.lastCount,
    lastRun: (r) => time(r.lastRun),
    saved: (r) => time(r.savedAt),
  })
  const searchPage = usePager(searchSort.sorted, `${searchSort.sort?.key}:${searchSort.sort?.dir}`)
  const orgSort = useSort(orgs, {
    name: (r) => r.name,
    location: (r) => (r.state ? `${r.state} ${r.city ?? ""}` : null),
    signal: (r) => (r.score == null ? null : Number(r.score)),
    saved: (r) => time(r.savedAt),
  })
  const orgPage = usePager(orgSort.sorted, `${orgSort.sort?.key}:${orgSort.sort?.dir}`)

  useEffect(() => {
    fetch("/api/user/saved-searches")
      .then((r) => r.json())
      .then((d) => setSearches(d.searches ?? []))
      .finally(() => setLoadingSearches(false))
    fetch("/api/user/saved-orgs")
      .then((r) => r.json())
      .then((d) => setOrgs(d.orgs ?? []))
      .finally(() => setLoadingOrgs(false))
  }, [])

  async function deleteSearch(id: string) {
    setDeletingSearchId(id)
    await fetch("/api/user/saved-searches", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id }),
    })
    setSearches((prev) => prev.filter((s) => s.id !== id))
    setDeletingSearchId(null)
  }

  async function deleteOrg(ein: string) {
    setDeletingOrgEin(ein)
    await fetch("/api/user/saved-orgs", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ein }),
    })
    setOrgs((prev) => prev.filter((o) => o.ein !== ein))
    setDeletingOrgEin(null)
  }

  return (
    <>
      <Nav />
      <main className="mx-auto max-w-7xl px-6 py-8">
        <div className="mb-8">
          <h1 className="font-serif text-3xl text-navy">Dashboard</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Your saved searches and watchlisted organizations.
          </p>
        </div>

        <section className="mb-12">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="font-serif text-xl text-navy">Saved Searches</h2>
            <span className="text-sm text-muted-foreground">{searches.length} saved</span>
          </div>
          {loadingSearches ? (
            <div className="flex items-center gap-2 py-8 text-sm text-muted-foreground">
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-navy border-t-transparent" />
              Loading…
            </div>
          ) : searches.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border px-6 py-10 text-center">
              <p className="text-sm text-muted-foreground">No saved searches yet.</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Use the <span className="font-medium text-navy">Save Search</span> button on any query page.
              </p>
            </div>
          ) : (
            <>
            <PagerBar pager={searchPage.pager} noun="saved searches" />
            <div className="overflow-x-auto rounded-lg border border-border">
              <table className="w-full text-sm">
                <thead>
                  <tr className="rder-b bg-muted/50 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    <SortableTh label="Name" sortKey="name" sort={searchSort.sort} onSort={searchSort.setSort} />
                    <SortableTh label="View" sortKey="view" sort={searchSort.sort} onSort={searchSort.setSort} />
                    <th className="px-4 py-3">Filters</th>
                    <SortableTh label="Last Count" sortKey="count" sort={searchSort.sort} onSort={searchSort.setSort} defaultDir="desc" align="right" />
                    <SortableTh label="Last Run" sortKey="lastRun" sort={searchSort.sort} onSort={searchSort.setSort} defaultDir="desc" />
                    <SortableTh label="Saved" sortKey="saved" sort={searchSort.sort} onSort={searchSort.setSort} defaultDir="desc" />
                    <th className="px-4 py-3" />
                  </tr>
                </thead>
                <tbody>
                  {searchPage.pageRows.map((s) => (
                    <tr key={s.id} className="border-b border-border/50 transition hover:bg-muted/30">
                      <td className="px-4 py-3 font-medium text-navy">{s.name}</td>
                      <td className="px-4 py-3">
                        <span className="rounded bg-muted px-1.5 py-0.5 text-xs font-medium">
                          {routeLabel(s.route)}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-xs text-muted-foreground max-w-[200px] truncate">
                        {Object.entries(s.params).map(([k, v]) => `${k}: ${v}`).join(" · ")}
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-sm">
                        {s.lastCount != null ? s.lastCount.toLocaleString() : "--"}
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">{formatDate(s.lastRun)}</td>
                      <td className="px-4 py-3 text-muted-foreground">{formatDate(s.savedAt)}</td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-3">
                          <Link href={buildSearchUrl(s.route, s.params)} className="text-sm font-medium text-navy hover:underline">
                            Run →
                          </Link>
                          <button
                         onClick={() => deleteSearch(s.id)}
                            disabled={deletingSearchId === s.id}
                            className="text-xs text-muted-foreground hover:text-red-500 disabled:opacity-40"
                          >
                            Remove
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <PagerNav pager={searchPage.pager} />
            </>
          )}
        </section>

        <section>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="font-serif text-xl text-navy">Watchlist</h2>
            <span className="text-sm text-muted-foreground">
              {orgs.length} organization{orgs.length !== 1 ? "s" : ""}
            </span>
          </div>
          {loadingOrgs ? (
            <div className="flex items-center gap-2 py-8 text-sm text-muted-foreground">
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-navy border-t-transparent" />
              Loading…
            </div>
          ) : orgs.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border px-6 py-10 text-center">
              <p className="text-sm text-muted-foreground">No organizations saved yet.</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Click the <span className="font-medium text-navy">bookmark icon</span> on any org row to add it here.
              </p>
            </div>
          ) : (
            <>
            <PagerBar pager={orgPage.pager} noun="organizations" />
            <div className="overflow-x-auto rounded-lg border border-border">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    <SortableTh label="Organization" sortKey="name" sort={orgSort.sort} onSort={orgSort.setSort} />
                    <SortableTh label="Location" sortKey="location" sort={orgSort.sort} onSort={orgSort.setSort} />
                    <SortableTh label="Signal" sortKey="signal" sort={orgSort.sort} onSort={orgSort.setSort} defaultDir="desc" />
                    <SortableTh label="Saved" sortKey="saved" sort={orgSort.sort} onSort={orgSort.setSort} defaultDir="desc" />
                    <th className="px-4 py-3" />
                  </tr>
                </thead>
                <tbody>
                  {orgPage.pageRows.map((o) => (
                    <tr key={o.ein} className="border-b border-border/50 transition hover:bg-muted/30">
                      <td className="px-4 py-3">
                        <Link href={`/org/${o.ein}`} className="font-medium text-navy hover:underline">
                          {o.name}
                        </Link>
                        <p className="text-xs text-muted-foreground">{o.ein}</p>
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">{o.city}, {o.state}</td>
                      <td className="px-4 py-3">
                        {o.tier ? <ScoreBadge tier={o.tier} score={o.score} /> : <span className="text-xs text-muted-foreground">--</span>}
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">{formatDate(o.savedAt)}</td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-3">
                          <Link href={`/org/${o.ein}`} className="text-sm font-medium text-navy hover:underline">
                            View →
                          </Link>
                          <button
                            onClick={() => deleteOrg(o.ein)}
                            disabled={deletingOrgEin === o.ein}
                            className="text-xs text-muted-foreground hover:text-red-500 disabled:opacity-40"
                          >
                            Remove
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <PagerNav pager={orgPage.pager} />
            </>
          )}
        </section>
      </main>
    </>
  )
}
