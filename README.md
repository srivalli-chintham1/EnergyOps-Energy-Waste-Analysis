# Energy waste & peak demand: synthetic dataset and generator

Correlates machine telemetry, production output, time-of-use tariffs and weather so that energy waste (idle load, intensity drift) and peak-demand events can be found, costed and traced to a recommendation.

## What is here

| Path | Purpose |
|---|---|
| `generate.py` | Single generator for starter and full scale (parameterised). Also holds the data dictionary, which drives the DDL and validation. |
| `validate.py` | Independent validator: reads only exported files and recomputes tariffs, reconciliation and lifecycles. |
| `reproduce.sh` | Regenerates twice with the same seed and compares SHA-256 checksums and row counts. |
| `full_dataset.zip` | Full run: 2 plants, 20 meters, 18 machines, 90 days x 15-min, 2,000 batches. |
| `starter_dataset/` | Small run (6 meters, 30 days, 200 batches) from the same generator. |
| `reproducibility_checksums.json` | Checksums from the reproducibility run. |

Each dataset folder contains: `data/*.csv` (all tables), `json/*.json` (all but the two largest tables), `sql/schema.sql` + `sql/seed.sql.gz`, `docs/data_dictionary.{md,csv}`, `ground_truth/ground_truth.{csv,json}`, `manifest.json` (source manifest, command, seed, checksums) and `validation_summary.{md,json}`.

## Run it

```
python generate.py --seed 20261022 --start 2026-07-01 --days 90 --plants 2 --meters 20 --batches 2000 --out out
python generate.py --scale starter --out starter
python validate.py out
./reproduce.sh
```
Needs Python 3.10+, numpy, pandas. Fixed seed `20261022`; scale is set by `--days --meters --batches --plants`.

## Results (full dataset)

- **Validation: 154 / 154 checks pass** (28 FK relationships, PK uniqueness for 18 tables, enums, date ordering, reconciliation, lifecycles, duplicates).
- **Reproducibility:** two regenerations with seed 20261022 matched on all 40 files and 366,160 data rows, byte for byte.
- Rows: 172,103 energy readings (172,073 after removing the 30 retransmissions, with 39 labelled meter gaps), 2,000 batches, 4,320 hourly weather rows, 11 recommendations.

## Model

**Entities** (all with PK, FKs and effective dates where relevant; see `docs/data_dictionary.md`): the 10 required (Plant, Meter, Machine, EnergyReading, ProductionBatch, Shift, Tariff, WeatherObservation, MaintenanceEvent, Recommendation) plus supporting tables: `MachineMeterAssignment` (N:M bridge), `TariffCalendar`, `StatusHistory` (append-only event log), `MachineStatePeriod` (RUN/IDLE/STANDBY periods) and four derived tables (`ReadingCost`, `DailyPlantSummary`, `BatchEnergy`, `MonthlyDemand`).

**Cardinality:** Plant 1:N Meter, Machine, Shift, Tariff; Meter(MAIN) 1:N Meter(SUB); Machine N:M Meter via bridge (each machine has a DIRECT_SUB and an INDIRECT_MAIN row); Machine 1:N ProductionBatch, MaintenanceEvent, MachineStatePeriod; Meter 1:N EnergyReading; Shift 1:N ProductionBatch; Recommendation N:1 Machine (optional, null for plant-level peak recs). `StatusHistory` references batches, maintenance and recommendations polymorphically.

**IDs:** `MTR-P01-001`, `ENG-<meter_id>-<YYYYMMDDTHHMMZ>`, `BATCH-2026-000001`, `TAR-2026-001`, `REC-2026-000001` (plus `MCH-`, `SHF-`, `MNT-2026-`, `WX-`, etc.). Counters zero-padded and immutable.

**Generation order:** master data, calendar/shifts/tariffs, weather, batches, waste scenarios, power model, readings, then injected anomalies, then derived tables, maintenance, recommendations, and lifecycle history.

**Rules driving outcomes (not random labels):**
- Machine state per 15 min is derived from the batch schedule and shift calendar: RUN (batch), IDLE (working shift, no batch), STANDBY (otherwise).
- Power = state kW x weather factor (weather-sensitive machines scale above 22 C) x noise. The MAIN meter = sum of its submeters + unmetered base load (HVAC/lighting, temperature- and occupancy-dependent). kWh = kW / 4.
- Waste scenarios: **high idle** (idle kW multiplied 2.2-3x (capped below run power)) and **intensity shift** (run kW up 15-25% at unchanged throughput). Each ends at a CORRECTIVE `MaintenanceEvent`, which keeps maintenance, scenario and recommendation lifecycles consistent.
- **Peak spikes:** 13 simultaneous-restart events inside the PEAK tariff band.
- Tariffs are effective-dated (a 6% rate change at day 45) with weekday/weekend windows; cost uses the plant-local time, day type and effective date of each interval.
- **Recommendations come from detector rules run on measured data** (`R-IDLE-1`: idle kW over 1.5x baseline for 5 consecutive days; `R-INT-1`: rolling median of 8 batches at least 10% over baseline intensity; `R-PEAK-1`: monthly PEAK-band maximum over 1.2x its p95). Each stores baseline, observed value, evidence window, expected savings (kWh or kW) and cost. They never read the ground truth.

## Injected edge cases (labelled in `ground_truth/`, 143 rows)

| issue_type | count | How it appears in input data |
|---|---|---|
| METER_GAP | 39 | Missing intervals (rows absent); register keeps counting |
| DUPLICATE_READING | 30 | Retransmitted row, same meter+interval, `ingest_seq=2`, id suffix `-R2` |
| KW_KWH_CONFUSION | 25 | `energy_kwh` holds the kW value (4x too large); `demand_kw_avg` is correct |
| MACHINE_OUTSIDE_METER_HIERARCHY | 25 | `machine_id` on a submeter reading not assigned to that meter |
| METER_TOTAL_MISMATCH | 3 | Register jumps more than interval energy; interval value correct |
| TARIFF_TIMEZONE_MISMATCH | 1 | One tariff row (P02 weekday PEAK, period 2) labelled `UTC` |
| PEAK_DEMAND_SPIKE | 13 | Four machines restart together in the PEAK band |
| HIGH_IDLE_CONSUMPTION / ENERGY_INTENSITY_SHIFT | 4 / 3 | Machine-level, with start/end window and multiplier |

Only the targeted rows are altered; every other row is untouched. `ground_truth.csv` has `expected_decision` and a JSON `detail` per row. No input table has a label column. The validator uses the ground truth only to check that each injected issue is detected by a rule, and that nothing is detected that is not in the ground truth.

## Acceptance criteria mapping

- **Energy totals reconcile:** register deltas equal interval energy on all unaffected rows; MAIN exceeds the submeter sum in every fully observed interval (overall unmetered share about 16% in the full run); daily totals equal the sum of reading costs.
- **Cost uses correct tariff interval:** validator recomputes the tariff for all 172k readings from UTC + plant timezone + calendar day type + effective date (0 mismatches).
- **Intensity normalised by output:** `DailyPlantSummary` and `BatchEnergy` report kWh/unit.
- **Recommendations cite baseline and savings:** see the Recommendation fields above.

## Assumptions and limits

- Fully synthetic; no external data, no personal data. `manifest.json` records an empty external-sources list. Plant names are fictional.
- Weather is a smooth diurnal/seasonal model with autocorrelated noise, not real observations. Timezone offsets are constant over the window (no DST change falls inside Jul-Sep).
- One machine per submeter, so attribution is clean by design. The bridge table supports N:M, but no relocations are generated.
- The `-R2` suffix on duplicates mimics an ingest-gateway convention; a model should not use it as a feature. The natural key is (meter, interval, ingest_seq).
- Where a gap overlaps a batch, `BatchEnergy.coverage_ratio < 1` and intensity is left null instead of imputed.
- Planted-effect sizes (multipliers, thresholds) are tunable constants near the top of `generate.py` and in the scenario block.
