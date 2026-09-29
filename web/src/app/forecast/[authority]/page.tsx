import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { DataTable } from "@/components/charts/ChartFrame";
import { PageHeader, Pushback } from "@/components/Section";
import { Status } from "@/components/Status";
import { formatValue as f } from "@/lib/format";
import { bundle, manifest } from "@/lib/load";

import { AuthorityClient } from "./AuthorityClient";

export function generateStaticParams() {
  return bundle().authorities.map((a) => ({ authority: a.authority }));
}

export async function generateMetadata({ params }: { params: Promise<{ authority: string }> }): Promise<Metadata> {
  const { authority } = await params;
  return { title: `${authority} forecast` };
}

export default async function AuthorityPage({ params }: { params: Promise<{ authority: string }> }) {
  const { authority } = await params;
  const b = bundle();
  const info = b.authorities.find((a) => a.authority === authority);
  if (!info) notFound();
  const m = manifest();
  const served = b.served_backend;
  const v = (key: string) => m.v(key);
  const region = b.regions.find((r) => r.code === info.region);
  const comparable = info.comparable && m.has(`skill.${served}.verdict.${authority}`);
  const verdict = comparable ? m.text(`skill.${served}.verdict.${authority}`) : "not comparable";
  const skillTable = m.table(`skill.${served}.h1_24.table`);
  const row = skillTable.rows.find((r) => String(r[0]) === authority);
  const byAuthority = m.table(`backtest.${served}.by_authority`);
  const backtestRow = byAuthority.rows.find((r) => String(r[0]) === authority);
  const status = verdict === "wins" ? "good" : verdict === "loses" ? "serious" : "warning";

  return (
    <>
      <PageHeader
        kicker={`${region?.label ?? info.region} region, ${info.interconnection} interconnection`}
        question={`${authority}: what does the desk see at the last origin, and how did the year go?`}
      >
        <p>
          {comparable ? (
            <>
              Over the test year at horizons 1 to 24 the {served} backend&apos;s MAPE was {row ? f(row[2], "pct2") : "n/a"} against the
              operator&apos;s {row ? f(row[3], "pct2") : "n/a"}, a skill of {row ? f(row[4], "spct1") : "n/a"} (interval{" "}
              {row ? f(row[5], "spct1") : ""} to {row ? f(row[6], "spct1") : ""}), and the verdict after correction is{" "}
              <Status kind={status}>{verdict}</Status>.
            </>
          ) : (
            <>
              The operator&apos;s published forecast for {authority} covers a different scope than its demand series, so this authority is graded
              against the seasonal naive only and left out of the wins and losses.
            </>
          )}{" "}
          Typical demand {f(info.typical_mw, "mw")}.
        </p>
      </PageHeader>

      <AuthorityClient
        authority={authority}
        served={served}
        fanCallout={`The actual is the ink line, the median the cyan lead, the 50 and 90 percent bands the cyan ramp, the operator's day ahead forecast the gold dashes, the seasonal naive dotted. Over the test year the ${served} backend's 90 percent bands covered ${backtestRow ? f(backtestRow[10], "pct1") : "n/a"} of ${authority}'s hours.`}
        fanProvenance={m.prov(`backtest.${served}.coverage_90`)}
        profileCallout={`Error grows with the horizon for every forecaster; the operator's line is flat because a day ahead forecast is issued once for the whole day. ${authority}'s MAPE over all horizons: ${backtestRow ? f(backtestRow[2], "pct2") : "n/a"} against the seasonal naive's ${backtestRow ? f(backtestRow[6], "pct2") : "n/a"}.`}
        profileProvenance={m.prov(`backtest.${served}.mape`)}
        weatherCallout={`Observed temperature at ${authority}'s stated location, which the model saw at the target hour: a real day ahead forecast sees a weather forecast instead. The heating and cooling thresholds were chosen on the validation year (${v(`backtest.own.threshold_candidates`)} candidate pairs per authority).`}
        weatherProvenance={m.prov("data.weather.rows")}
        reconciledCallout={`The base forecast of ${authority} beside the MinT reconciled one at the last origin. Across the hierarchy MinT ${m.text("hierarchy.verdict.mint.level3")} at the authority level (${v("hierarchy.base.level3.mape")} to ${v("hierarchy.mint.level3.mape")}).`}
        reconciledProvenance={m.prov("hierarchy.mint.level3.mape")}
      />

      <section className="card p-4 mt-5" aria-labelledby="skill-row">
        <h3 id="skill-row" className="font-display text-base mb-2">
          {authority}&apos;s row in the skill table, horizons 1 to 24
        </h3>
        {row ? (
          <DataTable table={{ columns: skillTable.columns, formats: skillTable.formats, rows: [row] }} dense label="Skill row" />
        ) : (
          <p className="text-sm text-ink2">Not in the skill table: the operator&apos;s forecast is not comparable for this authority.</p>
        )}
        {backtestRow ? (
          <div className="mt-3">
            <DataTable table={{ columns: byAuthority.columns, formats: byAuthority.formats, rows: [backtestRow] }} dense label="Backtest row" />
          </div>
        ) : null}
        <p className="text-xs text-ink2 mt-2">{m.prov(`skill.${served}.h1_24.wins`)}</p>
        <p className="text-sm mt-3">
          <Link href="/backtest/">The full skill table and the protocol</Link>
        </p>
      </section>

      <Pushback>
        <p>
          My forecast has a meteorologist behind it and yours saw the weather that happened. Both true: the comparison flatters the model on
          the days the weather forecast was wrong, and the skill on this page is an upper bound for that reason. The operator also forecasts
          its own scope; where EIA&apos;s demand series and the published forecast cover different footprints the authority is marked not
          comparable rather than counted as a win.
        </p>
      </Pushback>
    </>
  );
}
