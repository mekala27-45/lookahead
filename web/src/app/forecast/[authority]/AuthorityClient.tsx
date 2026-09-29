"use client";

import { useEffect, useState } from "react";

import { ChartFrame, DataTable } from "@/components/charts/ChartFrame";
import { LineChart } from "@/components/charts/LineChart";
import { SourceChip, useApiSource } from "@/components/Controls";
import { FanChart, type FanRow } from "@/components/FanChart";
import { Status } from "@/components/Status";
import { type Answer, ApiError, type ForecastOut, issueForecast } from "@/lib/api";
import { fmt } from "@/lib/format";
import { markReady } from "@/lib/ready";
import { useMart } from "@/lib/useMart";

interface FanMartRow extends FanRow {
  authority: string;
  origin: string;
  backend: string;
}
interface ProfileRow extends Record<string, unknown> {
  horizon: number;
  mape_model: number;
  mape_operator: number | null;
  mape_naive: number;
  coverage_90: number;
}
interface WeatherRow extends Record<string, unknown> {
  utc_hour: string;
  temperature_c: number | null;
  humidity_pct: number | null;
  heating_threshold_c: number | null;
  cooling_threshold_c: number | null;
}
interface ReconciledRow extends Record<string, unknown> {
  method: string;
  horizon: number;
  q50: number;
  actual: number | null;
}

const when = (iso: string) => iso.replace("T", " ").slice(0, 16) + " UTC";

export function AuthorityClient({
  authority,
  served,
  fanCallout,
  fanProvenance,
  profileCallout,
  profileProvenance,
  weatherCallout,
  weatherProvenance,
  reconciledCallout,
  reconciledProvenance,
}: {
  authority: string;
  served: string;
  fanCallout: string;
  fanProvenance: string;
  profileCallout: string;
  profileProvenance: string;
  weatherCallout: string;
  weatherProvenance: string;
  reconciledCallout: string;
  reconciledProvenance: string;
}) {
  const fan = useMart<FanMartRow>(`select * from mart_fan_latest where authority = '${authority}' and backend = '${served}' order by horizon`);
  const profile = useMart<ProfileRow>(
    `select horizon, mape_model, mape_operator, mape_naive, coverage_90 from mart_horizon_profile where authority = '${authority}' and backend = '${served}' order by horizon`,
  );
  const weather = useMart<WeatherRow>(`select * from mart_weather_recent where authority = '${authority}' order by utc_hour`);
  const reconciled = useMart<ReconciledRow>(
    `select method, horizon, q50, actual from mart_reconciled_latest where node = '${authority}' and method in ('base', 'mint') order by method, horizon`,
  );
  useEffect(() => {
    if (fan.rows || fan.error) markReady();
  }, [fan.rows, fan.error]);
  const origin = fan.rows?.[0]?.origin ? when(String(fan.rows[0].origin)) : "";

  return (
    <>
      <ChartFrame
        title={`${authority}: the last test origin${origin ? ` (${origin})` : ""}, 48 hours ahead`}
        callout={fanCallout}
        provenance={fanProvenance}
        table={
          fan.rows
            ? {
                columns: ["Hours ahead", "Target hour (UTC)", "5%", "25%", "Median", "75%", "95%", "Actual", "Operator", "Seasonal naive"],
                formats: ["int", "text", "mw", "mw", "mw", "mw", "mw", "mw", "mw", "mw"],
                rows: fan.rows.map((r) => [r.horizon, when(String(r.target_hour)), r.q05, r.q25, r.q50, r.q75, r.q95, r.actual, r.operator, r.naive]),
              }
            : null
        }
        testId="authority-fan"
      >
        {fan.rows ? <FanChart rows={fan.rows} testId="authority-fan-chart" /> : fan.error ? <p className="p-4 text-sm text-ink2">{fan.error}</p> : <div className="skeleton h-[300px]" />}
      </ChartFrame>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 mt-5">
        <ChartFrame
          title="Error by hour of horizon, against both baselines"
          callout={profileCallout}
          provenance={profileProvenance}
          table={
            profile.rows
              ? {
                  columns: ["Horizon", "Model MAPE", "Operator MAPE", "Seasonal naive MAPE", "90% coverage"],
                  formats: ["int", "pct2", "pct2", "pct2", "pct1"],
                  rows: profile.rows.map((r) => [r.horizon, r.mape_model, r.mape_operator, r.mape_naive, r.coverage_90]),
                }
              : null
          }
          testId="horizon-profile"
        >
          {profile.rows ? (
            <LineChart
              series={[
                { key: "model", name: `${served} forecast`, points: profile.rows.map((r) => ({ x: r.horizon, y: r.mape_model })), color: "var(--lead)", width: 2 },
                { key: "operator", name: "Operator", points: profile.rows.map((r) => ({ x: r.horizon, y: r.mape_operator })), color: "var(--cat-2)", dash: "6 4" },
                { key: "naive", name: "Seasonal naive", points: profile.rows.map((r) => ({ x: r.horizon, y: r.mape_naive })), color: "var(--cat-3)", dash: "2 3" },
              ]}
              xFmt="int"
              yFmt="pct1"
              xLabel="Hours ahead of the origin"
              yLabel="MAPE over the test year"
              height={260}
              xDomain={[1, 48]}
            />
          ) : (
            <div className="skeleton h-[260px]" />
          )}
        </ChartFrame>

        <ChartFrame
          title="The weather driver over the last three weeks, with the chosen thresholds"
          callout={weatherCallout}
          provenance={weatherProvenance}
          table={
            weather.rows
              ? {
                  columns: ["Hour (UTC)", "Temperature (C)", "Humidity (%)"],
                  formats: ["text", "float1", "float0"],
                  rows: weather.rows.map((r) => [when(String(r.utc_hour)), r.temperature_c, r.humidity_pct]),
                }
              : null
          }
          testId="weather-driver"
        >
          {weather.rows && weather.rows.length ? (
            <LineChart
              series={[
                {
                  key: "temperature",
                  name: "Observed temperature",
                  points: weather.rows.map((r, i) => ({ x: i, y: r.temperature_c })),
                  color: "var(--cat-6)",
                  width: 1.6,
                },
              ]}
              xFmt="int"
              yFmt="float1"
              xLabel="Hours from the start of the window"
              yLabel="Degrees Celsius, observed"
              height={260}
              zero={false}
              hRules={[
                { y: Number(weather.rows[0]?.heating_threshold_c ?? 0), label: "heating threshold", color: "var(--seq-3)", dash: "4 3" },
                { y: Number(weather.rows[0]?.cooling_threshold_c ?? 0), label: "cooling threshold", color: "var(--cat-6)", dash: "4 3" },
              ]}
            />
          ) : (
            <div className="skeleton h-[260px]" />
          )}
        </ChartFrame>
      </div>

      <div className="card p-4 mt-5" data-testid="reconciled">
        <h3 className="font-display text-base mb-1">The reconciled figure beside the base figure at the last origin</h3>
        <p className="text-sm text-ink2 mb-3">{reconciledCallout}</p>
        {reconciled.rows && reconciled.rows.length ? (
          <DataTable
            table={{
              columns: ["Hours ahead", "Base median", "MinT median", "Actual", "Base error", "MinT error"],
              formats: ["int", "mw", "mw", "mw", "spct1", "spct1"],
              rows: reconciled.rows
                .filter((r) => r.method === "base")
                .map((b) => {
                  const mint = reconciled.rows?.find((r) => r.method === "mint" && r.horizon === b.horizon);
                  const actual = b.actual;
                  return [
                    b.horizon,
                    b.q50,
                    mint?.q50 ?? null,
                    actual,
                    actual ? (b.q50 - actual) / actual : null,
                    actual && mint ? (mint.q50 - actual) / actual : null,
                  ];
                }),
            }}
            max={12}
            dense
            label="Base against MinT at the last origin"
          />
        ) : reconciled.error ? (
          <p className="text-sm text-ink2">{reconciled.error}</p>
        ) : (
          <div className="skeleton h-40" />
        )}
        <p className="text-xs text-ink2 mt-2">{reconciledProvenance}</p>
      </div>

      <IssueForecast authority={authority} />
    </>
  );
}

function IssueForecast({ authority }: { authority: string }) {
  const source = useApiSource();
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [answer, setAnswer] = useState<Answer<ForecastOut> | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  const issue = async () => {
    setBusy(true);
    setProblem(null);
    try {
      setAnswer(await issueForecast(authority, token));
    } catch (e) {
      setProblem(e instanceof ApiError ? `${e.status}: ${e.message}` : e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card p-4 mt-5" data-testid="issue-forecast" aria-labelledby="issue-title">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 id="issue-title" className="font-display text-base">
          Issue a forecast for {authority} through the API
        </h3>
        <SourceChip source={answer ? answer.source : source} testId="issue-source" />
      </div>
      <p className="text-sm text-ink2 mt-1">
        The API issues a forecast at the latest origin its data allows, stores its 48 rows with the model version and the origin, writes the
        audit row, then answers with the id. Writes need the token; without one, or while the API is asleep, the button shows the forecast the
        recording issued for this authority and says so.
      </p>
      <div className="flex flex-wrap items-end gap-3 mt-3">
        <label className="text-xs text-ink2">
          Write token (optional)
          <br />
          <input
            type="password"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            className="mt-1 w-56"
            autoComplete="off"
            data-testid="write-token"
            aria-label="Write token"
          />
        </label>
        <button
          type="button"
          onClick={issue}
          disabled={busy || source === "probing"}
          className="px-3 py-1.5 rounded border border-hairline bg-raised text-sm font-semibold hover:border-control disabled:opacity-60"
          data-testid="issue-button"
        >
          {busy ? "Issuing" : "Issue a forecast"}
        </button>
      </div>
      {problem ? (
        <p className="text-sm mt-3">
          <Status kind="critical">Refused</Status> <span className="text-ink2">{problem}</span>
        </p>
      ) : null}
      {answer ? (
        <div className="mt-3 text-sm" data-testid="issued">
          <p>
            Forecast id <span className="mono" data-testid="forecast-id">{answer.body.forecast_id}</span>, origin {when(answer.body.origin)}, model{" "}
            <span className="mono">{answer.body.model_version}</span>, {answer.body.stored_rows ?? answer.body.horizons} rows stored
            {answer.source === "recorded" ? " (recorded session: the API was asleep or no token was given)" : " (live)"}.
          </p>
          {answer.reason ? <p className="text-ink2 text-xs mt-1">{answer.reason}</p> : null}
          {answer.body.rows ? (
            <p className="text-ink2 text-xs mt-1">
              First hour median {fmt(answer.body.rows[0]?.q50 ?? null, "mw")}, 90 percent band {fmt(answer.body.rows[0]?.q05 ?? null, "mw")} to{" "}
              {fmt(answer.body.rows[0]?.q95 ?? null, "mw")}.
            </p>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
