import type { Metadata } from "next";

import { DataTable, type TableData } from "@/components/charts/ChartFrame";
import { PageHeader, Pushback, Section } from "@/components/Section";
import { bundle, manifest } from "@/lib/load";
import type { ManifestView } from "@/lib/manifest";

import { HierarchyClient } from "./HierarchyClient";

export const metadata: Metadata = { title: "Coherence" };

function table(m: ManifestView, key: string): TableData {
  const t = m.table(key);
  return { columns: t.columns, formats: t.formats, rows: t.rows };
}

export default function Hierarchy() {
  const m = manifest();
  const b = bundle();
  const v = (key: string) => m.v(key);
  return (
    <>
      <PageHeader kicker="Coherence" question="Do the regional forecasts add up to the national one, and did making them add up help?">
        <p>
          {v("hierarchy.nodes")} nodes: the lower 48, three interconnections, {v("data.hierarchy.regions")} regions, {v("hierarchy.authorities")}{" "}
          authorities, {v("hierarchy.subregions")} eligible subregions and {v("hierarchy.remainder_nodes")} remainder nodes so the leaves sum to their
          authority to the megawatt. Every node is forecast directly by the own backend over {v("hierarchy.origins")} origins, then reconciled
          three ways; the largest coherence gap after MinT is {v("hierarchy.coherence_gap_mw.mint")} MW, after bottom up{" "}
          {v("hierarchy.coherence_gap_mw.bottom_up")} MW, while the unreconciled base forecasts disagree by up to {v("hierarchy.coherence_gap_mw.base")}.
        </p>
        <p>
          The honest result: reconciliation helped at {v("hierarchy.helped_list")}; it hurt at {v("hierarchy.hurt_list")}. The method with the lowest
          error summed over levels is {v("hierarchy.best_method")}.
        </p>
      </PageHeader>

      <HierarchyClient
        authorities={b.authorities}
        regions={b.regions}
        treeCallout={`Each node's MAPE over the test year before reconciliation (gray) and after MinT (cyan). MinT ${m.text("hierarchy.verdict.mint.level0")} at the top (${v("hierarchy.base.level0.mape")} to ${v("hierarchy.mint.level0.mape")}) and ${m.text("hierarchy.verdict.mint.level4")} at the leaves (${v("hierarchy.base.level4.mape")} to ${v("hierarchy.mint.level4.mape")}). Regions open to their authorities and subregions.`}
        treeProvenance={m.prov("hierarchy.mint.level0.mape")}
        levelsCallout={`The MinT covariance is the Schafer and Strimmer shrinkage of the base residual covariance on the validation year, intensity ${v("hierarchy.shrinkage_intensity")}; top down splits the top forecast by the validation year's proportions and ${m.text("hierarchy.verdict.top_down.level4")} at the leaves.`}
        levelsProvenance={m.prov("hierarchy.by_level")}
      />

      <Section id="helped" title="Helped or hurt, by method and level">
        <div className="card p-4">
          <DataTable table={table(m, "hierarchy.helped_or_hurt")} dense label="Helped or hurt" />
          <p className="text-xs text-ink2 mt-2">{m.prov("hierarchy.helped_or_hurt")}</p>
        </div>
      </Section>

      <Section
        id="gap"
        title="The subregion gap in the source"
        intro={
          <p>
            EIA&apos;s subregion series do not exactly match their authority&apos;s demand: the mean absolute gap is {v("data.subregion_gap.mean_abs_pct")} of
            the authority&apos;s demand and the worst authority&apos;s is {v("data.subregion_gap.worst_abs_pct")}. The build never scales a subregion to
            fit; the remainder node carries the difference so the arithmetic holds.
          </p>
        }
      >
        <div className="card p-4">
          <DataTable table={table(m, "data.subregion_gap")} dense label="Subregion gap" />
          <p className="text-xs text-ink2 mt-2">{m.prov("data.subregion_gap.mean_abs_pct")}</p>
        </div>
      </Section>

      <Pushback>
        <p>
          Your hierarchy is EIA&apos;s, not mine. It is: the regions and interconnections are EIA&apos;s assignment and the subregions are the eight
          authorities that publish them, so an operator whose control areas are drawn differently would reconcile a different tree. The
          remainder nodes make the arithmetic honest but they are not places anyone dispatches for, and a method that helps the regional line
          while hurting a leaf is reported as exactly that, because the morning meeting reads the leaves too.
        </p>
      </Pushback>
    </>
  );
}
