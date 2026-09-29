import type { Metadata } from "next";

import { DataTable, type TableData } from "@/components/charts/ChartFrame";
import { PageHeader, Pushback, Section } from "@/components/Section";
import { manifest } from "@/lib/load";
import type { ManifestView } from "@/lib/manifest";

import { HouseholdsClient } from "./HouseholdsClient";

export const metadata: Metadata = { title: "The meter" };

function table(m: ManifestView, key: string): TableData {
  const t = m.table(key);
  return { columns: t.columns, formats: t.formats, rows: t.rows };
}

export default function Households() {
  const m = manifest();
  const v = (key: string) => m.v(key);
  return (
    <>
      <PageHeader kicker="The meter, the second hierarchy" question="Who carries the evening peak, and did the dynamic tariff move it?">
        <p>
          {v("meter.households_profiled")} of the {v("meter.households_release")} London households with a full profile over the year before the
          test period, clustered by load shape into {v("meter.clusters")} clusters (the count chosen by the silhouette on a validation half of the
          households, {v("meter.silhouette_chosen")}). Cluster {v("meter.top_peak_cluster")} ({v("meter.top_peak_cluster_shape")}) carries{" "}
          {v("meter.top_peak_cluster_share")} of the panel&apos;s weekday evening peak with {v("meter.top_peak_cluster_household_share")} of the
          households.
        </p>
        <p>
          The dynamic time of use group was recruited, not randomized. Under the pre-registered plan (hash {v("meter.tou.plan_hash_short")}), matched
          against standard tariff households in the same cluster with the nearest pre-period mean, the dynamic group used{" "}
          {v("meter.tou.response_pct")} (interval {v("meter.tou.response_pct_lower")} to {v("meter.tou.response_pct_upper")}) during the{" "}
          {v("meter.tou.events")} high price events of 2013, {v("meter.tou.response_kwh")} kWh per household per event, with a rebound of{" "}
          {v("meter.tou.rebound_pct")} in the three hours after. {v("meter.tou.types_rejected")} of {v("meter.tou.types")} event types are different
          from zero after Benjamini-Hochberg.
        </p>
      </PageHeader>

      <HouseholdsClient
        profilesCallout={`Weekday solid, weekend dashed, every panel on the same axis so a flat cluster reads as flat. Profiles are means over ${v("meter.profile_window_start")} to ${v("meter.profile_window_end")}; the shapes are named by rule from the weekday profile.`}
        profilesProvenance={m.prov("meter.clusters")}
        totalCallout={`A fixed panel of ${v("meter.forecast.households")} households reporting through the whole window (${v("meter.forecast.household_share")} of those profiled), forecast hourly by the gbm backend over ${v("meter.forecast.test_start")} to ${v("meter.forecast.test_end")} at ${v("meter.forecast.origins")} origins, without weather. MinT ${v("meter.forecast.mint_verdict_total")} at the total (${v("meter.forecast.base.level0.mape")} to ${v("meter.forecast.mint.level0.mape")}) and ${v("meter.forecast.mint_verdict_clusters")} at the clusters (${v("meter.forecast.base.level1.mape")} to ${v("meter.forecast.mint.level1.mape")}).`}
        totalProvenance={m.prov("meter.forecast.by_level")}
      />

      <Section id="clusters" title="The clusters and their share of the evening peak">
        <div className="card p-4">
          <DataTable table={table(m, "meter.clusters")} dense label="Clusters" />
          <p className="text-xs text-ink2 mt-2">{m.prov("meter.clusters")}</p>
        </div>
      </Section>

      <Section
        id="tou"
        title="The time of use response by event type, as pre-registered"
        intro={
          <p>
            {v("meter.tou.pairs")} matched pairs from {v("meter.tou.dtou_households")} dynamic tariff households and a pool of {v("meter.tou.std_pool")}{" "}
            standard ones ({v("meter.tou.dropped")} dropped for want of a candidate). Difference in differences per event against the same half
            hours on comparison days, {v("meter.tou.replicates")} block bootstrap replicates over events, plan hash {v("meter.tou.plan_hash")}.
          </p>
        }
      >
        <div className="card p-4">
          <DataTable table={table(m, "meter.tou.by_type")} dense label="Time of use response by event type" />
          <p className="text-xs text-ink2 mt-2">{m.prov("meter.tou.by_type")}</p>
        </div>
      </Section>

      <Section id="reconciliation" title="The meter reconciliation, before and after">
        <div className="card p-4">
          <DataTable table={table(m, "meter.forecast.by_level")} dense label="Meter forecast by level" />
          <p className="text-xs text-ink2 mt-2">{m.prov("meter.forecast.by_level")}</p>
        </div>
      </Section>

      <Section
        id="peak"
        title="Peak contribution: what a demand response program would target first"
        intro={
          <p>
            At a stated {v("meter.peak.value_gbp_per_kw")} pounds per kilowatt of evening peak reduction, the cluster to approach first is cluster{" "}
            {v("meter.peak.target_cluster")} ({v("meter.peak.target_shape")}), at {v("meter.peak.target_kw_per_household")} kW per household in the
            evening peak.
          </p>
        }
      >
        <div className="card p-4">
          <DataTable table={table(m, "meter.peak.contribution")} dense label="Peak contribution" />
          <p className="text-xs text-ink2 mt-2">{m.prov("meter.peak.contribution")}</p>
        </div>
      </Section>

      <Pushback>
        <p>
          The London households are from 2011 to 2014 and opted in, and the dynamic tariff group was recruited, not drawn by lot. Matching on
          cluster and pre-period consumption removes the differences we can see, not the ones we cannot: a household that chose a dynamic tariff
          may have been the kind that shifts load anyway, and no difference in differences can rule that out. The estimate is what the plan said
          it would be, no more; the pre-registration is what stops it from being tuned after the fact.
        </p>
      </Pushback>
    </>
  );
}
