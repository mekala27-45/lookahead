import type { Metadata } from "next";
import Link from "next/link";

import { IntervalColumns } from "@/components/charts/IntervalColumns";
import { PageHeader, Pushback } from "@/components/Section";
import { bundle, manifest } from "@/lib/load";

import { HomeClient } from "./HomeClient";

export const metadata: Metadata = { title: "Control room" };

export default function ControlRoom() {
  const m = manifest();
  const b = bundle();
  const served = b.served_backend;
  const v = (key: string) => m.v(key);
  const wins = m.num(`skill.${served}.h1_24.wins`);
  const losses = m.num(`skill.${served}.h1_24.losses`);
  const ties = m.num(`skill.${served}.h1_24.ties`);
  const comparable = m.num(`skill.${served}.h1_24.authorities`);
  const coverage = m.num(`backtest.${served}.coverage_90`);
  const points = [
    {
      key: "wins",
      short: "Beat",
      label: "Authorities where the model beat the operator",
      color: "var(--lead)",
      value: wins,
      low: m.num(`skill.${served}.h1_24.wins_lower`),
      high: m.num(`skill.${served}.h1_24.wins_upper`),
    },
    {
      key: "losses",
      short: "Lost",
      label: "Authorities where the operator beat the model",
      color: "var(--cat-2)",
      value: losses,
      low: m.num(`skill.${served}.h1_24.losses_lower`),
      high: m.num(`skill.${served}.h1_24.losses_upper`),
    },
    { key: "ties", short: "Tie", label: "Not distinguishable after correction", color: "var(--control)", value: ties, low: ties, high: ties },
  ];
  return (
    <>
      <PageHeader kicker={`The control room, as of ${m.asOf}`} question="Does the forecast beat the operator, and where does it not?">
        <p>
          Every balancing authority in the lower 48 publishes its own day ahead demand forecast. Over the test year, at horizons 1 to 24,
          the {served} backend beat the operator in {v(`skill.${served}.h1_24.wins`)} of {v(`skill.${served}.h1_24.authorities`)} comparable
          authorities and lost in {v(`skill.${served}.h1_24.losses`)}, after Benjamini-Hochberg; its 90 percent bands covered{" "}
          {v(`backtest.${served}.coverage_90`)} of the hours they claimed. The seasonal naive and the operator sit in every table on these pages.
        </p>
        <p className="text-ink2 text-base">
          Every figure here is read from the published manifest or queried from its marts in your browser. The models saw observed weather,
          which a real day ahead forecast does not have.
        </p>
      </PageHeader>

      <section aria-labelledby="headline" className="mb-5">
        <h2 id="headline" className="sr-only">
          The headline numbers
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          <div className="card p-5" data-testid="headline-wins">
            <p className="text-xs uppercase tracking-[0.12em] text-ink2">Authorities beaten, horizons 1 to 24</p>
            <p className="font-display text-[2.8rem] leading-none mt-3 num font-semibold" data-testid="headline-wins-value">
              {v(`skill.${served}.h1_24.wins`)}
              <span className="text-xl text-ink2 font-normal"> of {v(`skill.${served}.h1_24.authorities`)}</span>
            </p>
            <p className="text-sm text-ink2 mt-2">
              Interval {v(`skill.${served}.h1_24.wins_lower`)} to {v(`skill.${served}.h1_24.wins_upper`)} over bootstrap replicates of the
              test days.
            </p>
          </div>
          <div className="card p-5" data-testid="headline-losses">
            <p className="text-xs uppercase tracking-[0.12em] text-ink2">Authorities lost to the operator</p>
            <p className="font-display text-[2.8rem] leading-none mt-3 num font-semibold" data-testid="headline-losses-value">
              {v(`skill.${served}.h1_24.losses`)}
              <span className="text-xl text-ink2 font-normal"> of {v(`skill.${served}.h1_24.authorities`)}</span>
            </p>
            <p className="text-sm text-ink2 mt-2">
              Interval {v(`skill.${served}.h1_24.losses_lower`)} to {v(`skill.${served}.h1_24.losses_upper`)}; {v(`skill.${served}.h1_24.ties`)}{" "}
              ties. The losses are on the page with the wins.
            </p>
          </div>
          <div className="card p-5" data-testid="headline-coverage">
            <p className="text-xs uppercase tracking-[0.12em] text-ink2">90 percent bands, share of hours covered</p>
            <p className="font-display text-[2.8rem] leading-none mt-3 num font-semibold" data-testid="headline-coverage-value">
              {v(`backtest.${served}.coverage_90`)}
            </p>
            <p className="text-sm text-ink2 mt-2">
              Against a stated 90 percent, over {v(`backtest.${served}.rows_scored`)} scored rows; the 50 percent bands covered{" "}
              {v(`backtest.${served}.coverage_50`)}.
            </p>
          </div>
        </div>
      </section>

      <div className="card p-4 mb-5" data-testid="headline-columns">
        <IntervalColumns
          title="Wins, losses and ties against the operator, with intervals"
          subtitle={`${served} backend, horizons 1 to 24, ${comparable} comparable authorities, test year`}
          points={points}
          fmt="int"
          yDomain={[0, comparable]}
          height={180}
        />
        <p className="text-xs text-ink2 mt-2">{m.prov(`skill.${served}.h1_24.wins`)}</p>
      </div>

      <HomeClient
        tiles={b.tiles}
        authorities={b.authorities}
        regions={b.regions}
        fanCallout={`The reconciled lower 48 forecast at the last test origin: the leaves sum to this line to the megawatt (largest MinT gap ${v("hierarchy.coherence_gap_mw.mint")} MW). At the top of the hierarchy MinT ${m.text("hierarchy.verdict.mint.level0") === "helped" ? "improved" : "worsened"} the base forecast's MAPE, from ${v("hierarchy.base.level0.mape")} to ${v("hierarchy.mint.level0.mape")}.`}
        fanProvenance={m.prov("hierarchy.mint.level0.mape")}
        alertsCallout={`The detector raised ${v("events.test.alerts")} alerts over the test year across ${v("events.test.authorities")} authorities: ${v("events.test.demand_events")} demand events and ${v("events.test.data_defects")} data defects, at a threshold of ${v("events.threshold")} standardized residuals held for ${v("events.persistence_hours")} hours.`}
        alertsProvenance={m.prov("events.test.alerts")}
      />

      <section className="mt-10 grid grid-cols-1 md:grid-cols-3 gap-5" aria-label="Where to go next">
        {[
          ["/backtest/", "The protocol", `Rolling origins over ${v(`backtest.${served}.origins`)} authority days, the skill table, the reliability diagram, the cross check between backends and the recovery study.`],
          ["/hierarchy/", "Coherence", `${v("hierarchy.nodes")} nodes from the lower 48 to the subregion, three methods, accuracy before and after at every level.`],
          ["/events/", "Anomalies", `Recall ${v("events.known.recall")} on the known events table, the residual heatmap per authority and the operating point with both costs.`],
        ].map(([href, title, text]) => (
          <Link key={href} href={href ?? "/"} className="card p-4 no-underline hover:border-control">
            <p className="font-display text-lg">{title}</p>
            <p className="text-sm text-ink2 mt-1">{text}</p>
          </Link>
        ))}
      </section>

      <Pushback>
        <p>
          You used observed weather. Yes: the temperature and humidity the models saw at the target hour are what happened, not a forecast
          issued the evening before, and every figure that depends on them says so. A real day ahead desk has a meteorologist and a weather
          forecast; this build has neither, which flatters its error on the hot and cold days and is the first reason to read the losses as
          real and the wins as an upper bound. My forecast has local knowledge behind it: it does, and losing to it in{" "}
          {v(`skill.${served}.h1_24.losses`)} authorities is the expected honest result, not a bug.
        </p>
      </Pushback>
    </>
  );
}
