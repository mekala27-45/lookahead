import type { Metadata } from "next";
import type { ReactNode } from "react";

import { DataTable, type TableData } from "@/components/charts/ChartFrame";
import { ReadyWithoutQueries } from "@/components/Controls";
import { bundle, manifest } from "@/lib/load";
import type { ManifestView } from "@/lib/manifest";

import { PrintButton } from "./PrintButton";

export const metadata: Metadata = { title: "The operations review" };

function table(m: ManifestView, key: string): TableData {
  const t = m.table(key);
  return { columns: t.columns, formats: t.formats, rows: t.rows };
}

function Exhibit({ m, id, title, children, max = 60 }: { m: ManifestView; id: string; title: string; children?: ReactNode; max?: number }) {
  return (
    <figure className="my-6" data-exhibit={id}>
      <figcaption className="font-sans text-sm font-semibold mb-2">{title}</figcaption>
      {children ?? <DataTable table={table(m, id)} dense={false} max={max} label={title} />}
      <p className="font-sans text-xs text-ink2 mt-2">{m.prov(id)}</p>
    </figure>
  );
}

export default function Report() {
  const m = manifest();
  const b = bundle();
  const served = b.served_backend;
  const v = (key: string) => m.v(key);
  const t = (key: string) => m.text(key);
  return (
    <>
      <ReadyWithoutQueries />
      <div className="flex flex-wrap items-center justify-between gap-3 mb-6 no-print">
        <p className="text-xs uppercase tracking-[0.14em] text-ink2">The operations review, as a memo for the monthly meeting</p>
        <PrintButton />
      </div>
      <article className="report-sheet card px-5 py-8 sm:px-12 sm:py-12 max-w-[1040px]" data-testid="memo">
        <div className="memo">
          <p className="font-sans text-xs uppercase tracking-[0.14em] text-ink2">Load desk operations review · as of {m.asOf}</p>
          <h1 className="text-[2rem] leading-tight mt-2 mb-6">The forecast against the operator, the year in review</h1>

          <h2>1. Skill against the operator</h2>
          <p>
            Over the test year, at horizons 1 to 24, the served backend ({served}) beat the operator&apos;s published day ahead forecast in{" "}
            {v(`skill.${served}.h1_24.wins`)} of {v(`skill.${served}.h1_24.authorities`)} comparable balancing authorities (interval{" "}
            {v(`skill.${served}.h1_24.wins_lower`)} to {v(`skill.${served}.h1_24.wins_upper`)}), lost in {v(`skill.${served}.h1_24.losses`)} (
            {v(`skill.${served}.h1_24.losses_lower`)} to {v(`skill.${served}.h1_24.losses_upper`)}) and tied in {v(`skill.${served}.h1_24.ties`)}, after
            Benjamini-Hochberg across the authorities. Pooled over the comparable hours its MAPE was {v(`skill.${served}.h1_24.model_mape_pooled`)}{" "}
            against the operator&apos;s {v(`skill.${served}.h1_24.operator_mape_pooled`)}, a skill of {v(`skill.${served}.h1_24.skill_pooled`)}; the
            median authority&apos;s skill was {v(`skill.${served}.h1_24.median_skill`)}. {v("skill.not_comparable_authorities")} authorities are not
            counted because the published forecast covers a different scope than the demand series: {v("skill.not_comparable_list")}.
          </p>
          <p>
            Over all 48 horizons the {served} backend&apos;s MAPE was {v(`backtest.${served}.mape`)} ({v(`backtest.${served}.mape_lower`)} to{" "}
            {v(`backtest.${served}.mape_upper`)}) against the seasonal naive&apos;s {v(`backtest.${served}.mape_naive`)} and the operator&apos;s{" "}
            {v(`backtest.${served}.mape_operator`)} on the paired hours, a MASE of {v(`backtest.${served}.mase`)} and a CRPS of {v(`backtest.${served}.crps`)}.
            At the daily peak its absolute error was {v(`backtest.${served}.peaks.model_peak_abs`)} against the operator&apos;s{" "}
            {v(`backtest.${served}.peaks.operator_peak_abs`)}, with a median timing error of {v(`backtest.${served}.peaks.model_timing_median`)} hours.
          </p>
          <Exhibit m={m} id={`skill.${served}.h1_24.table`} title={`Exhibit 1. Skill against the operator by authority, ${served}, horizons 1 to 24`} />
          <Exhibit m={m} id="skill.crosscheck" title="Exhibit 2. The cross check: own against gbm, the seasonal naive and the operator beside them" />

          <h2>2. Coverage</h2>
          <p>
            The 90 percent bands covered {v(`backtest.${served}.coverage_90`)} of the test year&apos;s hours ({v(`backtest.${served}.coverage_90_lower`)} to{" "}
            {v(`backtest.${served}.coverage_90_upper`)}) and the 50 percent bands {v(`backtest.${served}.coverage_50`)}. On the validation year the
            calibration held {v(`backtest.${served}.validation_coverage_90`)} at the 90 percent level, inside the gate&apos;s band of{" "}
            {v("policy.coverage_band_90_low")} to {v("policy.coverage_band_90_high")}. Shares of actuals at or below each served level:{" "}
            {v(`backtest.${served}.reliability.q05`)}, {v(`backtest.${served}.reliability.q25`)}, {v(`backtest.${served}.reliability.q50`)},{" "}
            {v(`backtest.${served}.reliability.q75`)} and {v(`backtest.${served}.reliability.q95`)} against 5, 25, 50, 75 and 95 percent;{" "}
            {v(`backtest.${served}.degenerate_levels`)} levels are degenerate.
          </p>
          <Exhibit m={m} id={`backtest.${served}.by_horizon`} title={`Exhibit 3. Error and coverage by hour of horizon, ${served}, with both baselines`} max={48} />

          <h2>3. Where reconciliation helped and where it hurt</h2>
          <p>
            {v("hierarchy.nodes")} nodes from the lower 48 to the subregion, forecast directly and reconciled by bottom up, top down and MinT (shrinkage
            intensity {v("hierarchy.shrinkage_intensity")}). Every reconciled set is coherent to within {v("hierarchy.coherence_gap_mw.mint")} MW; the
            base forecasts disagree by up to {v("hierarchy.coherence_gap_mw.base")}. Reconciliation helped at {v("hierarchy.helped_list")} and hurt at{" "}
            {v("hierarchy.hurt_list")}; the method with the lowest error summed over levels is {v("hierarchy.best_method")}. At the top MinT moved the
            MAPE from {v("hierarchy.base.level0.mape")} to {v("hierarchy.mint.level0.mape")}; at the leaves from {v("hierarchy.base.level4.mape")} to{" "}
            {v("hierarchy.mint.level4.mape")}.
          </p>
          <Exhibit m={m} id="hierarchy.helped_or_hurt" title="Exhibit 4. Helped or hurt, by method and level" />

          <h2>4. The events the detector caught and missed</h2>
          <p>
            The detector watches the day&apos;s own forecast residual, standardized per authority, past {v("events.threshold")} for{" "}
            {v("events.persistence_hours")} hours; hours a quarantine rule flagged are data defects, never demand events. It detected{" "}
            {v("events.known.detected")} of the {v("events.known.rows")} rows of the known events table ({v("events.known.recall")}), with a median delay of{" "}
            {v("events.known.median_delay_hours")} hours, and raised {v("events.known.false_alarms_outside")} alerts in the{" "}
            {v("events.known.hours_outside")} window hours outside the events. Missed: {v("events.known.missed_list")}. Over the real test year it raised{" "}
            {v("events.test.alerts")} alerts, {v("events.test.demand_events")} demand events and {v("events.test.data_defects")} data defects. On the
            demonstration grid it recovered {v("events.sim.defects_recovered")} of {v("events.sim.defects")} planted defects as defects and{" "}
            {v("events.sim.load_sheds_detected")} of {v("events.sim.load_sheds")} planted load sheds, with {v("events.sim.false_alarms")} false alarms.
          </p>
          <Exhibit m={m} id="events.known.table" title="Exhibit 5. The known events, with detection hours" />

          <h2>5. The meter</h2>
          <p>
            {v("meter.households_profiled")} London households in {v("meter.clusters")} load shape clusters; cluster {v("meter.top_peak_cluster")} (
            {v("meter.top_peak_cluster_shape")}) carries {v("meter.top_peak_cluster_share")} of the weekday evening peak. Under the pre-registered plan (hash{" "}
            {v("meter.tou.plan_hash_short")}), the dynamic time of use group used {v("meter.tou.response_pct")} ({v("meter.tou.response_pct_lower")} to{" "}
            {v("meter.tou.response_pct_upper")}) during the {v("meter.tou.events")} high price events against matched standard households,{" "}
            {v("meter.tou.response_kwh")} kWh per household per event, with a rebound of {v("meter.tou.rebound_pct")} afterwards; {v("meter.tou.types_rejected")}{" "}
            of {v("meter.tou.types")} event types are distinguishable from zero after correction. The cluster forecast, reconciled by MinT, moved the panel
            total&apos;s MAPE from {v("meter.forecast.base.level0.mape")} to {v("meter.forecast.mint.level0.mape")} and the clusters&apos; from{" "}
            {v("meter.forecast.base.level1.mape")} to {v("meter.forecast.mint.level1.mape")}. A program buying peak reduction at{" "}
            {v("meter.peak.value_gbp_per_kw")} pounds per kilowatt would approach cluster {v("meter.peak.target_cluster")} first.
          </p>
          <Exhibit m={m} id="meter.tou.by_type" title="Exhibit 6. The time of use response by event type" />
          <Exhibit m={m} id="meter.peak.contribution" title="Exhibit 7. Peak contribution by cluster" />

          <h2>6. The live log and the registry</h2>
          <p>
            The API serves the {v("registry.served")} backend, chosen by {v("registry.gates")} gates ({v("registry.served_reason")}); the separate client
            verification is {v("deploy.status")}, reading back {v("deploy.forecast_rows_read_back")} rows with the audit row before the response:{" "}
            {v("deploy.audit_before_response")}. The live browser check {t("live.status")}. Latency of issuing a forecast: {v("latency.measurements")}{" "}
            measurement files on record.
          </p>

          <h2>7. Limitations</h2>
          <p>
            The models saw observed weather at the target hour; a real day ahead forecast sees a weather forecast, so every error figure here is a
            lower bound on what a live desk would see and every win against the operator an upper bound. The operator&apos;s forecast is compared only
            where its scope matches the demand series. The hierarchy is EIA&apos;s. The detector&apos;s threshold was chosen on the simulator because the
            real validation year has no labelled events. The London panel is from 2011 to 2014, opted in, and the tariff group was not randomized; the
            meter forecast uses a fixed panel of {v("meter.forecast.households")} households and no weather. The live scorecard scores against the committed
            actuals until the refresh job exists.
          </p>

          <h2>What the operator would push back on</h2>
          <p>
            You used observed weather, my forecast has a meteorologist behind it, your hierarchy is mine and not yours, and your households are a
            decade old and volunteered. All four are true and each is stated where it applies: the weather caveat on every figure that uses it, the
            comparability rule that drops {v("skill.not_comparable_authorities")} authorities rather than counting them, the remainder nodes that keep
            the arithmetic honest without pretending to be control areas, and the pre-registered plan that stops the tariff estimate from being tuned.
            What the build did not do is give the model a weather forecast, and it says so first.
          </p>
          <p className="font-sans text-sm text-ink2 mt-8" data-statement>
            {b.statement}
          </p>
        </div>
      </article>
    </>
  );
}
