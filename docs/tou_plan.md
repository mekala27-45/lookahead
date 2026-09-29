# Pre-registered analysis plan: the dynamic time of use tariff in Low Carbon London

Written before the household readings were examined for this question. The hash of this file
is recorded in results/meter/plan.json and rendered in the report; the analysis code reads the
plan's parameters from `lookahead_meter.plan`, which quotes the values below.

## The question

Did households on the dynamic time of use tariff (dToU) use less electricity during the high
price periods of the 2013 schedule than comparable households on the standard tariff, and by
how much, in percent and in kilowatt hours per household per event?

## What the comparison is

The dToU group was recruited, not randomized. The estimate is an observational difference in
differences against matched standard tariff households, and the report says so before any
number.

## Population

Every household in the release that has readings in the pre-period (1 October to 31 December
2012) and in 2013. The dToU households are the treated group. The comparison pool is every
standard tariff household with the same coverage.

## Matching

Each dToU household is matched to one standard tariff household, without replacement, in the
same load shape cluster (clusters from the profile clustering, chosen on the year before the
meter test period), with the nearest mean half hourly consumption in the pre-period. Matching
is done on the households sorted by identifier, and a dToU household with no unmatched
candidate left in its cluster is dropped and counted.

## Events

A high price event is a maximal run of consecutive half hours whose tariff band is High in the
2013 schedule. Event types, for the family of comparisons, are the four periods of the day the
event starts in: night (00:00 to 05:59), morning (06:00 to 11:59), afternoon (12:00 to 16:59),
evening (17:00 to 23:59).

## Outcome

For each event and household: mean kilowatt hours per half hour during the event's half hours
on the event day, and the mean over the same half hours on the comparison days, which are the
days of the same weekday or weekend type within fourteen days either side of the event day on
which none of those half hours is a High band.

## Estimator

Per event: the difference in differences of the treated mean and the matched control mean,
event day minus comparison days, in kilowatt hours per half hour per household; the percent
response is that difference divided by the matched controls' event day mean. The rebound is
the same estimator on the three hours after the event ends.

## Uncertainty

Block bootstrap over events in their calendar order, blocks of four consecutive events, five
hundred replicates, ninety percent percentile intervals, for the overall estimate and for each
event type. The two sided bootstrap p value per event type is twice the smaller tail share of
replicates at or across zero, and Benjamini-Hochberg at q 0.05 is applied across the four
types.

## What is reported

The overall response in percent and in kWh per household per event with its interval; the
response by event type after correction; the rebound; the number of events, treated
households, matched pairs and dropped households; and a paragraph on what a non randomized
comparison cannot say.
