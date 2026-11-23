// app/api/query/market-scan/route.ts
// Q1 — Market Scan: scored org list filtered by geo, NTEE, revenue

import { NextRequest, NextResponse } from 'next/server'
import * as duckdb from 'duckdb-async'
import { z } from 'zod'
import { getDbPath } from '@/lib/db'

const Schema = z.object({
  states: z.string().transform(v => v.split(',').map(s => s.trim().toUpperCase())),
  ntee_major: z.string().default('').transform(v => v ? v.split(',').map(s => s.trim().toUpperCase()) : []),
  rev_min: z.coerce.number().int().min(0).default(0),
  rev_max: z.coerce.number().int().max(999_999_999).default(999_999_999),
  sort: z.enum(['name', 'location', 'sector', 'revenue', 'score', 'tenure']).optional(),
  dir: z.enum(['asc', 'desc']).default('desc'),
  limit: z.coerce.number().int().min(1).max(200).default(50),
  offset: z.coerce.number().int().min(0).default(0),
})

const SORT_COLUMNS: Record<string, string[]> = {
  name: ['LOWER(o.name)'],
  location: ['o.state', 'LOWER(o.city)'],
  sector: ['COALESCE(o.ntee_code, o.ntee_code_classified)'],
  revenue: ['f.total_revenue'],
  score: ['ts.score'],
  tenure: ['ts.ceo_tenure_years'],
}

function buildOrderBy(sort: string | undefined, dir: 'asc' | 'desc'): string {
  const cols = sort ? SORT_COLUMNS[sort] : undefined
  const lead = cols ? cols.map(c => `${c} ${dir.toUpperCase()} NULLS LAST`).join(', ') + ', ' : ''
  return `${lead}ts.score DESC NULLS LAST, f.total_revenue DESC NULLS LAST, o.ein`
}

export async function GET(req: NextRequest) {
  const params = Object.fromEntries(req.nextUrl.searchParams)
  const parsed = Schema.safeParse(params)
  if (!parsed.success) {
    return NextResponse.json({ error: parsed.error.flatten() }, { status: 400 })
  }

  const { states, ntee_major, rev_min, rev_max, limit, offset, sort, dir } = parsed.data
  const dbPath = getDbPath()

  // Build IN clauses with individual placeholders
  const statePlaceholders = states.map(() => '?').join(', ')
  const nteeClause = ntee_major.length > 0
    ? `AND LEFT(COALESCE(o.ntee_code, o.ntee_code_classified), 1) IN (${ntee_major.map(() => '?').join(', ')})`
    : ''

  const SQL = `
    SELECT
      o.ein,
      o.name,
      o.city,
      o.state,
      COALESCE(o.ntee_code, o.ntee_code_classified) AS ntee_code,
      COALESCE(o.ntee_category, o.ntee_category_classified) AS ntee_category,
      (o.ntee_code IS NULL AND o.ntee_code_classified IS NOT NULL) AS ntee_ai,
      f.tax_year,
      f.total_revenue,
      f.total_expenses,
      (f.total_revenue - f.total_expenses) AS operating_surplus,
      f.total_assets,
      f.total_liabilities,
      ts.score,
      ts.total_score_v2,
      ts.tier,
      ts.consecutive_deficit,
      ts.ceo_tenure_years,
      ts.ceo_name,
      ts.ceo_comp,
      ts.ceo_comp_pct_ntee,
      ts.signal_leadership,
      ts.factors
    FROM organizations o
    JOIN (
      SELECT ein, MAX(tax_year) AS latest_year
      FROM filings
      GROUP BY ein
    ) latest ON o.ein = latest.ein
    JOIN filings f ON f.ein = o.ein AND f.tax_year = latest.latest_year
    LEFT JOIN transition_scores ts ON ts.ein = o.ein
    WHERE
      o.state IN (${statePlaceholders})
      ${nteeClause}
      AND COALESCE(f.total_revenue, 0) BETWEEN ? AND ?
    ORDER BY ${buildOrderBy(sort, dir)}
    LIMIT ? OFFSET ?
  `

  const COUNT_SQL = `
    SELECT COUNT(*) AS total
    FROM organizations o
    JOIN (
      SELECT ein, MAX(tax_year) AS latest_year
      FROM filings GROUP BY ein
    ) latest ON o.ein = latest.ein
    JOIN filings f ON f.ein = o.ein AND f.tax_year = latest.latest_year
    LEFT JOIN transition_scores ts ON ts.ein = o.ein
    WHERE
      o.state IN (${statePlaceholders})
      ${nteeClause}
      AND COALESCE(f.total_revenue, 0) BETWEEN ? AND ?
  `

  const db = await duckdb.Database.create(dbPath, { access_mode: 'READ_ONLY' })
  const conn = await db.connect()

  try {
    const baseArgs = [...states, ...ntee_major]

    const [rows, countResult] = await Promise.all([
      conn.all(SQL, ...baseArgs, rev_min, rev_max, limit, offset),
      conn.all(COUNT_SQL, ...baseArgs, rev_min, rev_max),
    ])

    return NextResponse.json({
      total: Number(countResult[0].total),
      limit,
      offset,
      results: rows,
    })
  } finally {
    await conn.close()
    await db.close()
  }
}
