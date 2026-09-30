# Provenance

Rendered from the manifest; every count below is a manifest value. Three sources, each named
with its terms; the raw London file is never committed.

## EIA-930, the Hourly Electric Grid Monitor

Publisher: U.S. Energy Information Administration, https://www.eia.gov/electricity/gridmonitor/.
Files: every six month `EIA930_BALANCE_<year>_<Jan_Jun|Jul_Dec>.csv` and
`EIA930_SUBREGION_<year>_<Jan_Jun|Jul_Dec>.csv` from 2018_Jul_Dec to
2026_Jul_Dec (17 balance files,
17 subregion files), downloaded from
`https://www.eia.gov/electricity/gridmonitor/sixMonthFiles/` without a key. Terms: U.S. government
work in the public domain. Columns used: the balancing authority, the UTC hour, demand, the day
ahead demand forecast, net generation, total interchange, and the subregion demand. Derived and
committed: `data/eia930/hourly.parquet` (3,877,346 rows, the raw demand with
every quarantine flag), `subregions.parquet`, `quarantine.parquet`, `subregion_gap.parquet`,
`authorities.csv`, `windows.json`, and `data/hierarchy.csv` (165 nodes).
Authorities in the files: 70, of which
58 report demand and 12
are generation only (AVRN, DEAA, EEI, GLHB, GRID, GRIF, GWA, HGMA, SEPA, SIKE, WWA, YAD). Revisions where a later file
changed an earlier hour: 0 (the later value kept).

## Open-Meteo historical weather

Publisher: Open-Meteo, https://open-meteo.com/, the historical weather API (ERA5 and its
successors), pulled once per authority location and year range without a key and cached under
`data/external/weather/`. Terms: CC BY 4.0, attribution "Weather data by Open-Meteo.com".
Locations: `data/locations.csv`, one stated location per authority with the reason for the choice.
Committed: `data/weather/hourly.parquet` (3,679,344 rows for
51 authorities, 2018-07-01 01:00:00+00:00 to
2026-09-23 00:00:00+00:00, 0 null temperatures) and
`data/weather/ATTRIBUTION.md`.

## Low Carbon London

Publisher: UK Power Networks on the London Datastore, "SmartMeter Energy Consumption Data in
London Households", https://data.london.gov.uk/dataset/smartmeter-energy-use-data-in-london-households.
Files: the consolidated half hourly CSV (in `LCL-FullData.zip`) and the 2013 dynamic time of use
tariff schedule (`Tariffs.xlsx`), fetched by `make data` into `data/external/london/` and never
committed. Terms: CC BY 4.0. Read in full into DuckDB: 167,932,474 readings from
5,566 households (1,123 on the dynamic
tariff, 4,443 standard), 2011-11-23 09:00:00 to
2014-02-28 00:00:00; 5,560 null readings,
115,453 duplicated readings and 506,645
missing half hours found by the checks. Only cluster level, event level and per household count
tables are committed under `results/meter/`; no household identifier leaves the machine.

## The simulator

`data/sim/` holds the demonstration seed of the synthetic grid: 8
authorities, 4 subregions, 26,280 hours, 16
planted events, the truth table and the specification. It is generated, not sourced.

> Demand data from the U.S. Energy Information Administration's Hourly Electric Grid Monitor, public domain; weather from Open-Meteo under CC BY 4.0; household data from UK Power Networks' Low Carbon London release under CC BY 4.0. Forecasts here are demonstrations and not for grid operations.
