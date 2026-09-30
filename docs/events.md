# Events and anomalies

**Detection.** The residual of the day's own forecast at horizons 1 to 24 against the raw
demand, as a share of the forecast, standardized per authority by the median and the scaled
median absolute deviation of the same residual over the validation year (the own backend's
expanding validation run, exported beside its conformal offsets). An hour is abnormal when the
standardized residual passes the threshold or when a quarantine rule flagged its raw value. A run
of at least 3 consecutive abnormal hours is an alert; a run
of flagged hours is an alert at any length, because a feed that reports a zero is a defect however
short.

**Classification.** A run that is at least half flagged, with normal neighbors, is a data defect;
a run of unflagged hours past the threshold is a demand event. A zero from a dead feed is never
a demand collapse (`tests/events`).

**The operating point.** The threshold is chosen on the demonstration grid's validation year,
where the simulator plants one event of each kind per authority, by the stated costs: a false
alarm costs 1.0, a missed load shed 25.0,
over the grid 2, 2.5, 3, 3.5, 4, 5, 6. Chosen: 6.0 (cost
5.0), interior: no. The real validation year has
no labelled events, which is why the choice is made where the truth is known and the standardized
scale is what carries it to the real grid.

| Threshold | False alarms | Missed load sheds | Cost |
|---:|---:|---:|---:|
| 2.0 | 702 | 0 | 702.0 |
| 2.5 | 324 | 0 | 324.0 |
| 3.0 | 140 | 0 | 140.0 |
| 3.5 | 65 | 0 | 65.0 |
| 4.0 | 29 | 0 | 29.0 |
| 5.0 | 15 | 0 | 15.0 |
| 6.0 | 5 | 0 | 5.0 |

Source: simulated, model own, the demonstration grid, validation year for the choice and test year for the grade, seed 13, as of 2026-09-29.

**Grading on the demonstration grid's test year.** Load sheds detected
1 of 2; defects recovered as
defects 6 of 6; defects called events
0; false alarms 8 among
9 demand event alerts. By condition and seed the recovery study
repeats the choice and the grading inside each run.

**The known events.** `data/known_events.csv`: 5 events in
10 rows, each with an onset, an end and a citation. For each row the own
backend is fit on the year before a window of ten days either side of the event, so the residuals
in the window are those of a model that has seen nothing after each origin. Detected
3 of 10 (30%), median
delay 5.7 hours; 0
false alarms in 4,924 hours outside the events
(0.00 per thousand hours). Missed:
covid_2020 at NYIS, covid_2020 at MISO, ida_2021 at MISO.8910, ida_2021 at MISO, elliott_2022 at TVA, elliott_2022 at DUK, elliott_2022 at CPLE.

| Event | Node | Onset (UTC) | Verdict | Detection hour (UTC) | Delay hours | Peak z | False alarms in window |
|---|---|---|---|---|---:|---:|---:|
| covid_2020 | NYIS | 2020-03-16 00:00 | missed | none | not applicable | not applicable | 0 |
| covid_2020 | MISO | 2020-03-18 00:00 | missed | none | not applicable | not applicable | 0 |
| uri_2021 | ERCO | 2021-02-15 07:20 | detected | 2021-02-15 13:00 | 5.7 | 8.9 | 0 |
| ida_2021 | MISO.8910 | 2021-08-29 17:00 | missed | none | not applicable | not applicable | 0 |
| ida_2021 | MISO | 2021-08-29 17:00 | missed | none | not applicable | not applicable | 0 |
| elliott_2022 | TVA | 2022-12-23 15:31 | missed | none | not applicable | not applicable | 0 |
| elliott_2022 | DUK | 2022-12-24 11:00 | missed | none | not applicable | not applicable | 0 |
| elliott_2022 | CPLE | 2022-12-24 11:00 | missed | none | not applicable | not applicable | 0 |
| beryl_2024 | ERCO.COAS | 2024-07-08 09:00 | detected | 2024-07-08 12:00 | 3.0 | 19.2 | 0 |
| beryl_2024 | ERCO | 2024-07-08 09:00 | detected | 2024-07-08 20:00 | 11.0 | 7.4 | 0 |

Source: real:eia930, model own, the known events table, each in a window of ten days either side, as of 2026-09-29.

**The real test year.** 277 alerts across 51
authorities (71 demand events, 206
data defects), 0.62 per thousand hours; the median residual
scale across authorities is 4.58%.

> Demand data from the U.S. Energy Information Administration's Hourly Electric Grid Monitor, public domain; weather from Open-Meteo under CC BY 4.0; household data from UK Power Networks' Low Carbon London release under CC BY 4.0. Forecasts here are demonstrations and not for grid operations.
