import type { Metadata } from "next";

import { DataTable, type TableData } from "@/components/charts/ChartFrame";
import { PageHeader, Pushback, Section } from "@/components/Section";
import { bundle, manifest } from "@/lib/load";
import type { ManifestView } from "@/lib/manifest";

import { EventsClient } from "./EventsClient";

export const metadata: Metadata = { title: "Anomalies" };

function table(m: ManifestView, key: string): TableData {
  const t = m.table(key);
  return { columns: t.columns, formats: t.formats, rows: t.rows };
}

export default function Events() {
  const m = manifest();
  const b = bundle();
  const v = (key: string) => m.v(key);
  return (
    <>
      <PageHeader kicker="Anomalies" question="Which drops in demand were events, which were dead feeds, and did the detector catch the ones we know about?">
        <p>
          The detector standardizes the day&apos;s own forecast residual per authority by the validation year&apos;s robust scale and raises an alert
          when it stays past {v("events.threshold")} for {v("events.persistence_hours")} consecutive hours. An hour a quarantine rule flagged (a
          zero, a negative, a duplicated or missing hour) is a data defect, never a demand event. The threshold was chosen on the demonstration
          grid&apos;s validation year at a false alarm cost of {v("events.false_alarm_cost")} and a missed event cost of {v("events.missed_event_cost")},
          from a grid of {v("events.grid_low")} to {v("events.grid_high")}; the choice is interior: {v("events.interior")}.
        </p>
        <p>
          On the known events table it detected {v("events.known.detected")} of {v("events.known.rows")} rows ({v("events.known.recall")}) with a median
          delay of {v("events.known.median_delay_hours")} hours from the onset, and raised {v("events.known.false_alarms_outside")} demand event alerts
          in the {v("events.known.hours_outside")} hours of the windows outside the events ({v("events.known.false_alarms_per_1000_hours")} per
          thousand hours). Missed: {v("events.known.missed_list")}.
        </p>
      </PageHeader>

      <EventsClient
        authorities={b.authorities}
        defaultAuthority={b.authorities.find((a) => a.authority === "ERCO") ? "ERCO" : (b.authorities[0]?.authority ?? "")}
        knownEvents={b.known_events}
        heatmapCallout={`Rust is over forecast, cyan is under forecast, clipped at six standard residuals. Over the test year the detector raised ${v("events.test.alerts")} alerts across ${v("events.test.authorities")} authorities (${v("events.test.demand_events")} demand events, ${v("events.test.data_defects")} data defects), ${v("events.test.alerts_per_1000_hours")} per thousand hours; ${v("events.test.low_share")} of the demand events were drops.`}
        heatmapProvenance={m.prov("events.test.alerts")}
        knownCallout={`The own backend was fit on the year before each window, so the forecast has seen nothing after its origin; the shaded span is the event as cited.`}
        knownProvenance={m.prov("events.known.recall")}
      />

      <Section id="known" title="The known events table, with detection hours">
        <div className="card p-4">
          <DataTable table={table(m, "events.known.table")} dense label="Known events" />
          <p className="text-xs text-ink2 mt-2">{m.prov("events.known.table")}</p>
        </div>
      </Section>

      <Section id="operating" title="The operating point, with both costs">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <div className="card p-4">
            <h3 className="font-display text-base mb-2">Cost on the demonstration grid&apos;s validation year, by threshold</h3>
            <DataTable table={table(m, "events.operating_grid")} dense label="Operating grid" />
            <p className="text-xs text-ink2 mt-2">{m.prov("events.threshold")}</p>
          </div>
          <div className="card p-4 text-sm space-y-2">
            <h3 className="font-display text-base">Graded on the demonstration grid&apos;s test year</h3>
            <p>
              Planted load sheds detected: {v("events.sim.load_sheds_detected")} of {v("events.sim.load_sheds")} ({v("events.sim.recall_load_shed")}).
              Planted defects recovered as defects: {v("events.sim.defects_recovered")} of {v("events.sim.defects")}; defects reported as demand
              events: {v("events.sim.defects_called_events")}. Demand event alerts {v("events.sim.demand_alerts")}, of which {v("events.sim.false_alarms")}{" "}
              overlapped no planted event (precision {v("events.sim.precision")}).
            </p>
            <p className="text-ink2">
              Per condition and seed, the recovery study on the backtest page repeats this grading with the threshold chosen inside each run. The
              real test year&apos;s alerts are unlabelled: the table above lists them with their class, and the known events windows are where recall
              is measured.
            </p>
          </div>
        </div>
      </Section>

      <Section id="test-year" title="Alerts by authority over the test year">
        <div className="card p-4">
          <DataTable table={table(m, "events.test.by_authority")} dense max={60} label="Alerts by authority" />
          <p className="text-xs text-ink2 mt-2">{m.prov("events.test.by_authority")}</p>
        </div>
      </Section>

      <Pushback>
        <p>
          A detector that watches its own forecast&apos;s residual only sees what the forecast did not expect, and a forecast that adapts to
          yesterday stops being surprised by a collapse on its second day; that is why the COVID rows are graded as sustained drops and why a
          gradual decline can be missed while a load shed is caught in its first hour. The threshold was chosen where the truth is known, on
          the simulator, because the real validation year has no labelled events; the real test year&apos;s alerts are reported, not judged.
        </p>
      </Pushback>
    </>
  );
}
