import type { Metadata } from "next"
import { Logo } from "@/components/logo"

export const metadata: Metadata = {
  title: "What DMV nonprofits pay their top people | SectorWindow",
  description:
    "A free benchmark built from 18,259 Form 990 filings in DC, Maryland and Virginia. Pay by sector and by revenue size.",
}

const MAIL_BODY = [
  "Hi David,",
  "",
  "Please send me the DMV nonprofit pay report.",
  "",
  "My organization:",
  "My sector:",
  "Annual revenue (a rough range is fine):",
  "",
  "Thank you.",
].join("\n")

const MAILTO = `mailto:david@davidedgertonjr.com?subject=${encodeURIComponent(
  "DMV pay report"
)}&body=${encodeURIComponent(MAIL_BODY)}`

const INSIDE = [
  "Pay by revenue band, from under $500K to $100M and above",
  "Pay by sector, across ten sector groups",
  "A sector-by-size map, so you can compare organizations like yours",
  "CEO and executive director pay on its own",
  "All 26 NTEE categories in an appendix",
  "Plain-language notes on method and limits",
]

const AUDIENCE = [
  "Executive directors and CEOs checking where they stand",
  "Board chairs and compensation committees setting pay",
  "HR and finance leaders preparing a review",
  "Search committees about to open a leadership search",
]

const STATS = [
  { n: "$134K", t: "Median pay for the highest-paid person at DMV nonprofits that pay anyone." },
  { n: "11x", t: "The gap between the smallest organizations ($56K) and the largest ($609K)." },
  { n: "$68K to $295K", t: "The range of median pay across sectors, from religion-related to mutual and membership organizations." },
]

function Check() {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" className="mt-1 h-5 w-5 shrink-0 text-teal-700" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 10.5l4 4 8-9" />
    </svg>
  )
}

export default function DmvPayReportPage() {
  return (
    <div className="min-h-screen bg-white text-navy">
      <header className="border-b border-border bg-white">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
          <Logo href="/dmv-pay-report" className="h-8 w-auto" />
          <span className="text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground">
            Free DMV report
          </span>
        </div>
      </header>

      <main>
        {/* Hero */}
        <section className="bg-navy text-white">
          <div className="mx-auto grid max-w-6xl items-center gap-12 px-6 py-16 md:grid-cols-[1.15fr_0.85fr] md:py-20">
            <div>
              <p className="mb-4 text-xs font-semibold uppercase tracking-[0.16em] text-teal">
                Free benchmark report
              </p>
              <h1 className="font-serif text-5xl font-semibold leading-[1.04] md:text-6xl">
                What do DMV nonprofits really pay their top people?
              </h1>
              <p className="mt-6 max-w-xl text-lg text-navy-100">
                A benchmark built from 18,259 Form 990 filings in DC, Maryland and Virginia. Pay by sector and by revenue size, in one nine-page report.
              </p>
              <a
                href={MAILTO}
                className="mt-8 inline-block rounded-md bg-teal px-7 py-4 text-base font-semibold text-navy transition hover:bg-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-white"
              >
                Email me for the free report
              </a>
              <p className="mt-4 text-sm text-navy-100">
                Tap the button and your email app opens with a short note ready to send. I reply with the PDF.
              </p>
            </div>
            <div className="relative mx-auto h-[400px] w-full max-w-[420px]" aria-hidden="true">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src="/reports/dmv-cover.jpg" alt="" className="absolute left-0 top-0 z-10 w-[62%] -rotate-3 rounded-sm bg-white shadow-2xl" />
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src="/reports/dmv-chart.jpg" alt="" className="absolute right-0 top-16 w-[62%] rotate-3 rounded-sm bg-white shadow-2xl" />
            </div>
          </div>
        </section>

        {/* Stats */}
        <section aria-label="Headline findings" className="border-b border-border bg-navy-50">
          <div className="mx-auto grid max-w-6xl gap-8 px-6 py-12 md:grid-cols-3">
            {STATS.map((s) => (
              <div key={s.n}>
                <div className={`font-serif font-bold leading-none text-navy ${s.n.length > 8 ? "pt-3 text-4xl" : "text-5xl"}`}>
                  {s.n}
                </div>
                <p className="mt-3 text-sm text-muted-foreground">{s.t}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Inside and audience */}
        <section className="mx-auto grid max-w-6xl gap-14 px-6 py-16 md:grid-cols-2">
          <div>
            <h2 className="mb-5 font-serif text-3xl font-semibold">What is inside</h2>
            <ul className="divide-y divide-border border-y border-border">
              {INSIDE.map((t) => (
                <li key={t} className="flex gap-3 py-3"><Check />{t}</li>
              ))}
            </ul>
          </div>
          <div>
            <h2 className="mb-5 font-serif text-3xl font-semibold">Who it is for</h2>
            <ul className="divide-y divide-border border-y border-border">
              {AUDIENCE.map((t) => (
                <li key={t} className="flex gap-3 py-3"><Check />{t}</li>
              ))}
            </ul>
          </div>
        </section>

        {/* Second call to action */}
        <section className="bg-teal-50">
          <div className="mx-auto max-w-6xl px-6 py-16">
            <h2 className="max-w-xl font-serif text-4xl font-semibold leading-tight">
              Planning a leadership search or a pay review?
            </h2>
            <p className="mt-4 max-w-2xl text-lg text-muted-foreground">
              Email me with your sector and annual revenue, and I will add the peer figures for an organization your size before we talk. A 20-minute call is the next step.
            </p>
            <a
              href={MAILTO}
              className="mt-8 inline-block rounded-md bg-navy px-7 py-4 text-base font-semibold text-white transition hover:bg-teal hover:text-navy focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-navy"
            >
              Email me for the report and a call
            </a>
          </div>
        </section>

        {/* About */}
        <section className="mx-auto max-w-6xl px-6 py-16">
          <h2 className="mb-4 font-serif text-3xl font-semibold">About SectorWindow</h2>
          <p className="max-w-3xl text-muted-foreground">
            SectorWindow is a nonprofit data platform built from public IRS filings. It tracks financial and leadership signals for more than 370,000 organizations across DC, Maryland, Virginia, Minnesota, New York, Delaware, Pennsylvania and New Jersey. It was built by David Edgerton Jr., Managing Partner of DEJ Search, a boutique retained executive search firm serving nonprofit, association and social-impact organizations.
          </p>
        </section>
      </main>

      <footer className="border-t border-border">
        <div className="mx-auto max-w-6xl px-6 py-8 text-xs text-muted-foreground">
          Source: public IRS Form 990 filings, tax year 2023, Part VII. Pay is the amount each organization itself reports paying its highest-paid person. Pay from related organizations and benefits are not counted. These are descriptive benchmarks, not compensation advice.
        </div>
      </footer>
    </div>
  )
}
