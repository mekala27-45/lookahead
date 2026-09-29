import type { Metadata } from "next";

import { DataTable, type TableData } from "@/components/charts/ChartFrame";
import { PageHeader, Pushback, Section } from "@/components/Section";
import { bundle, manifest } from "@/lib/load";
import type { ManifestView } from "@/lib/manifest";

import { BacktestClient, type BacktestTables } from "./BacktestClient";

export const metadata: Metadata = { title: "The backtest" };

function table(m: ManifestView, key: string): TableData {
  const t = m.table(key);
  return { columns: t.columns, formats: t.formats, rows: t.rows };
}

export default function Backtest() {
  const m = manifest();
  const b = bundle();
  const served = b.served_backend;
  const v = (key: string) => m.v(key);
  const backends = b.backends.filter((x) => m.has(`backtest.${x}.mape`));
  const models = backends.filter((x) => x !== "seasonal_naive");
  const tables: BacktestTables = { byAuthority: {}, byHorizon: {}, peaks: {} };
  for (const x of models) {
    tables.byAuthority[x] = table(m, `backtest.${x}.by_authority`);
    tables.byHorizon[x] = table(m, `backtest.${x}.by_horizon`);
    tables.peaks[x] = table(m, `backtest.${x}.peaks_by_authority`);
  }
  const both = models.includes("own") && models.includes("gbm");

  return (
    <>
      <PageHeader kicker="The protocol and its results" question="Could the backtest have flattered the model?">
        <p>
          One origin per day per authority at {v("policy.issue_hour_utc")}:00 UTC, horizons 1 to {v("policy.horizons")}, the last{" "}
          {v("policy.test_months")} months as the test period and the {v("policy.validation_months")} before as validation for every choice.
          Features are built through a point in time frame that cannot read past the origin, and a test recomputes a sample of rows from the raw
          tables to prove it. Intervals are block bootstraps over test days ({v("policy.bootstrap_replicates")} replicates of{" "}
          {v("policy.bootstrap_block_days")} day blocks); every family of comparisons across authorities is corrected by Benjamini-Hochberg at q{" "}
          {v("policy.bh_q")}.
        </p>
        <p>
          The {served} backend ran {v(`backtest.${served}.origins`)} authority origins in {v(`backtest.${served}.run_seconds`)} seconds (
          {v(`backtest.${served}.origins_per_minute`)} origins a minute on CPU), a MAPE of {v(`backtest.${served}.mape`)} over all horizons against the
          seasonal naive&apos;s {v(`backtest.${served}.mape_naive`)} and the operator&apos;s {v(`backtest.${served}.mape_operator`)} on the paired hours.
        </p>
      </PageHeader>

      <BacktestClient
        backends={backends}
        served={served}
        tables={tables}
        skillCallout={`Skill is one minus the model's MAPE over the operator's on the same target hours. In the headline band the ${served} backend wins in ${v(`skill.${served}.h1_24.wins`)} comparable authorities, loses in ${v(`skill.${served}.h1_24.losses`)} and ties in ${v(`skill.${served}.h1_24.ties`)} after correction; ${v("skill.not_comparable_authorities")} authorities are left out because the published forecast covers a different scope than the demand series.`}
        skillProvenance={m.prov(`skill.${served}.h1_24.wins`)}
        reliabilityCallout={`A calibrated forecaster's share of actuals at or below each level lies on the diagonal. ${served}: ${v(`backtest.${served}.reliability.q05`)} at the 5 percent level, ${v(`backtest.${served}.reliability.q50`)} at the median, ${v(`backtest.${served}.reliability.q95`)} at the 95 percent level; ${v(`backtest.${served}.degenerate_levels`)} served levels sit at zero or one hundred on validation, so the interior test ${m.text(`backtest.${served}.levels_interior`) === "yes" ? "passes" : "fails"}.`}
        reliabilityProvenance={m.prov(`backtest.${served}.reliability.q05`)}
        recoveryCallout={`${v("recovery.conditions")} conditions, ${v("recovery.seeds_per_condition")} seeds each on a grid with known truth. The harness is furthest from the known skill under ${v("recovery.worst_condition_for_harness")}; coverage is furthest from nominal under ${v("recovery.worst_condition_for_coverage")}.`}
        recoveryProvenance={m.prov("recovery.runs")}
        tablesProvenance={m.prov(`backtest.${served}.mape`)}
      />

      <Section
        id="crosscheck"
        title="The cross check: own against gbm on the same rows, both baselines beside them"
        intro={
          <p>
            {both
              ? `own has the lower error in ${v("skill.crosscheck.own_better")} authorities and gbm in ${v("skill.crosscheck.gbm_better")}; the two fall on different sides of the operator in ${v("skill.crosscheck.disagreements")} of ${v("skill.crosscheck.authorities")}. Where they disagree the page says so; nothing is averaged.`
              : "Only one backend has run so far; the cross check fills in when both have."}
          </p>
        }
      >
        <div className="card p-4">
          <DataTable table={table(m, "skill.crosscheck")} dense max={60} label="Cross check" />
          <p className="text-xs text-ink2 mt-2">{m.prov("skill.crosscheck")}</p>
        </div>
      </Section>

      <Section id="protocol" title="The protocol, stated in full">
        <div className="prose text-sm space-y-2">
          <p>
            Origins: one per day per authority at {v("policy.issue_hour_utc")}:00 UTC, the evening before in every U.S. time zone, which is when a
            day ahead process issues. Horizons 1 to {v("policy.horizons")}. Test: the last {v("policy.test_months")} months of the data.
            Validation: the {v("policy.validation_months")} months before, for the thresholds ({v("policy.heating_thresholds")} C heating,{" "}
            {v("policy.cooling_thresholds")} C cooling), the ridge penalty ({v("policy.ridge_penalties")}), the conformal calibration per{" "}
            {v("policy.conformal_horizon_bucket_hours")} hour horizon bucket and the served levels ({v("policy.quantile_levels")}). Training:
            everything earlier, expanding at each origin for own; gbm refits every {v("policy.gbm_refit_months")} month on the previous{" "}
            {v("policy.gbm_training_window_days")} days.
          </p>
          <p>
            Availability: a lag is allowed only if its hour is at or before the origin, so the same hour lag is 24 hours for the first day and 48
            for the second. Baselines: the seasonal naive at {v("policy.seasonal_naive_lag_hours")} hours with stated fallbacks, and the
            operator&apos;s published day ahead forecast read from the data. Intervals: block bootstrap over test days,{" "}
            {v("policy.bootstrap_replicates")} replicates of {v("policy.bootstrap_block_days")} day blocks at the {v("policy.interval_level")} level.
            Benjamini-Hochberg at q {v("policy.bh_q")} across authorities in every family. Every seeded step sorts before it draws.
          </p>
          <p>{v(`backtest.${served}.weather_caveat`)}</p>
        </div>
      </Section>

      <Pushback>
        <p>
          A backtest with a dozen places to leak the future is only as honest as its tests. This one recomputes feature rows from the raw tables
          at their origin, refuses a deliberately leaky lag, and ran first on a simulator where the truth is known: the harness&apos;s measured
          skill sits {v("recovery.base.harness.skill_bias")} from the known skill on the base condition, and its intervals cover the known value{" "}
          {v("recovery.base.harness.interval_covers_known")} of the time. What it cannot do is give the model a weather forecast instead of the
          weather that happened; that caveat is on every figure that uses it.
        </p>
      </Pushback>
    </>
  );
}
