# Data dictionary

Generated from `generate.py` (single source of truth for schema, SQL DDL and validation).
Key: PK = primary key; FK targets are given in the rule column. `-` = not applicable.

## Plant (`plant.csv`, source table)

| field | type | req | allowed values | unit | key | validation rule |
|---|---|---|---|---|---|---|
| plant_id | str | Y | P<nn> | - | PK | pattern P\d{2}; immutable |
| plant_name | str | Y | - | - | - | non-empty |
| timezone | str | Y | IANA zone | - | - | valid zone; tariff windows are interpreted in this zone |
| latitude | float | Y | -90..90 | deg | - | range check |
| longitude | float | Y | -180..180 | deg | - | range check |
| currency | enum | Y | USD,EUR | - | - | one currency per plant |
| status | enum | Y | ACTIVE,INACTIVE | - | - | lifecycle state |
| commissioned_date | date | Y | - | - | - | <= first reading date |

## Meter (`meter.csv`, source table)

| field | type | req | allowed values | unit | key | validation rule |
|---|---|---|---|---|---|---|
| meter_id | str | Y | MTR-<plant>-NNN | - | PK | zero-padded counter per plant; 001 is the MAIN meter |
| plant_id | str | Y | - | - | - | FK Plant.plant_id |
| meter_type | enum | Y | MAIN,SUB | - | - | exactly one MAIN per plant |
| parent_meter_id | str | N | - | - | - | FK Meter.meter_id; null for MAIN; SUB parent is the MAIN of the same plant |
| energy_unit | enum | Y | kWh | - | - | interval energy unit |
| demand_unit | enum | Y | kW | - | - | demand unit; kW = kWh x 60 / sampling_minutes |
| sampling_minutes | int | Y | 15 | min | - | equals interval length of readings |
| install_date | date | Y | - | - | - | <= first reading date |
| register_start_kwh | float | Y | >=0 | kWh | - | cumulative register value at start of first interval |
| status | enum | Y | ACTIVE,INACTIVE | - | - | lifecycle state |

## Machine (`machine.csv`, source table)

| field | type | req | allowed values | unit | key | validation rule |
|---|---|---|---|---|---|---|
| machine_id | str | Y | MCH-<plant>-NNN | - | PK | zero-padded counter per plant |
| plant_id | str | Y | - | - | - | FK Plant.plant_id |
| machine_type | enum | Y | PRESS,INJECTION_MOLDER,CNC_MILL,COMPRESSOR,OVEN,CHILLER,CONVEYOR | - | - | - |
| rated_kw | float | Y | >0 | kW | - | full-load power |
| idle_kw | float | Y | >0 | kW | - | nominal idle draw; < 0.5 x rated_kw |
| standby_kw | float | Y | >0 | kW | - | nominal draw outside working shifts |
| units_per_hour | float | Y | >0 | units/h | - | nominal throughput |
| weather_sensitive | bool | Y | 0,1 | - | - | 1 = load scales with outdoor temperature above 22 C |
| commissioned_date | date | Y | - | - | - | <= first batch |
| status | enum | Y | ACTIVE,INACTIVE | - | - | lifecycle state |

## MachineMeterAssignment (`machine_meter_assignment.csv`, source table)

| field | type | req | allowed values | unit | key | validation rule |
|---|---|---|---|---|---|---|
| assignment_id | str | Y | MMA-<plant>-NNN | - | PK | zero-padded per plant |
| machine_id | str | Y | - | - | - | FK Machine.machine_id |
| meter_id | str | Y | - | - | - | FK Meter.meter_id; same plant as machine |
| relation | enum | Y | DIRECT_SUB,INDIRECT_MAIN | - | - | N:M bridge; each machine has one DIRECT_SUB and one INDIRECT_MAIN row |
| effective_from | date | Y | - | - | - | - |
| effective_to | date | N | - | - | - | null = open; >= effective_from |

## Shift (`shift.csv`, source table)

| field | type | req | allowed values | unit | key | validation rule |
|---|---|---|---|---|---|---|
| shift_id | str | Y | SHF-<plant>-YYYYMMDD-<A/B/C> | - | PK | one row per plant, local date, shift code |
| plant_id | str | Y | - | - | - | FK Plant.plant_id |
| shift_date | date | Y | - | - | - | local date the shift starts |
| shift_code | enum | Y | A,B,C | - | - | A 06-14, B 14-22, C 22-06 (local) |
| start_utc | datetime | Y | - | UTC | - | < end_utc |
| end_utc | datetime | Y | - | UTC | - | 8 hours after start |
| is_working | bool | Y | 0,1 | - | - | A/B on weekdays, A on Saturdays, none on Sundays/holidays, C never |

## TariffCalendar (`tariff_calendar.csv`, source table)

| field | type | req | allowed values | unit | key | validation rule |
|---|---|---|---|---|---|---|
| calendar_id | str | Y | TCAL-<plant>-YYYYMMDD | - | PK | - |
| plant_id | str | Y | - | - | - | FK Plant.plant_id |
| calendar_date | date | Y | - | - | - | local date |
| day_type | enum | Y | WEEKDAY,WEEKEND | - | - | weekends and holidays are WEEKEND |
| holiday_name | str | N | - | - | - | set only for holidays |

## Tariff (`tariff.csv`, source table)

| field | type | req | allowed values | unit | key | validation rule |
|---|---|---|---|---|---|---|
| tariff_id | str | Y | TAR-2026-NNN | - | PK | zero-padded counter |
| plant_id | str | Y | - | - | - | FK Plant.plant_id |
| day_type | enum | Y | WEEKDAY,WEEKEND | - | - | - |
| tou_band | enum | Y | OFFPEAK,SHOULDER,PEAK | - | - | - |
| window_start_local | str | Y | HH:MM | - | - | local clock; window wraps midnight if start > end |
| window_end_local | str | Y | HH:MM | - | - | exclusive |
| timezone | str | Y | IANA zone | - | - | must equal the plant timezone |
| rate_per_kwh | float | Y | >0 | currency/kWh | - | - |
| demand_charge_per_kw | float | Y | >=0 | currency/kW-month | - | > 0 only for PEAK band |
| currency | enum | Y | USD,EUR | - | - | equals plant currency |
| effective_from | date | Y | - | - | - | windows of one plant+day_type+effective period tile 24 h with no overlap |
| effective_to | date | N | - | - | - | null = open |

## WeatherObservation (`weather_observation.csv`, source table)

| field | type | req | allowed values | unit | key | validation rule |
|---|---|---|---|---|---|---|
| weather_id | str | Y | WX-<plant>-YYYYMMDDHH | - | PK | hour is UTC |
| plant_id | str | Y | - | - | - | FK Plant.plant_id |
| observed_at_utc | datetime | Y | - | UTC | - | hourly |
| temperature_c | float | Y | -30..50 | C | - | - |
| relative_humidity_pct | float | Y | 0..100 | % | - | - |
| source | enum | Y | SYNTHETIC | - | - | no external data used |

## ProductionBatch (`production_batch.csv`, source table)

| field | type | req | allowed values | unit | key | validation rule |
|---|---|---|---|---|---|---|
| batch_id | str | Y | BATCH-2026-NNNNNN | - | PK | ordered by start_utc then machine_id |
| plant_id | str | Y | - | - | - | FK Plant.plant_id |
| machine_id | str | Y | - | - | - | FK Machine.machine_id; same plant; no overlapping batches per machine |
| shift_id | str | Y | - | - | - | FK Shift.shift_id; shift containing start_utc, must be working |
| product_code | enum | Y | PRD-A,PRD-B,PRD-C,PRD-D | - | - | - |
| start_utc | datetime | Y | - | UTC | - | 15-minute aligned |
| planned_end_utc | datetime | Y | - | UTC | - | > start_utc |
| end_utc | datetime | Y | - | UTC | - | actual end; <= planned_end_utc (earlier if ABORTED) |
| units_planned | int | Y | >0 | units | - | - |
| units_produced | int | Y | >=0 | units | - | <= units_planned |
| status | enum | Y | COMPLETED,ABORTED | - | - | must equal last StatusHistory.to_state |

## EnergyReading (`energy_reading.csv`, source table)

| field | type | req | allowed values | unit | key | validation rule |
|---|---|---|---|---|---|---|
| reading_id | str | Y | ENG-<meter_id>-<YYYYMMDDTHHMMZ>[-R2] | - | PK | -R2 suffix = retransmitted copy added by the ingest gateway |
| meter_id | str | Y | - | - | - | FK Meter.meter_id |
| interval_start_utc | datetime | Y | - | UTC | - | 15-minute aligned; natural key with meter_id + ingest_seq |
| interval_end_utc | datetime | Y | - | UTC | - | start + 15 min |
| energy_kwh | float | Y | >=0 | kWh | - | interval energy; expected = demand_kw_avg / 4 |
| demand_kw_avg | float | Y | >=0 | kW | - | average demand over the interval |
| demand_kw_peak | float | Y | >=demand_kw_avg | kW | - | maximum demand within the interval |
| register_kwh | float | Y | >=0 | kWh | - | cumulative register at interval end; delta = interval energy |
| machine_id | str | N | - | - | - | FK Machine.machine_id; machine behind a SUB meter; null on MAIN meters |
| ingest_seq | int | Y | 1,2 | - | - | 2 = retransmission |

## MaintenanceEvent (`maintenance_event.csv`, source table)

| field | type | req | allowed values | unit | key | validation rule |
|---|---|---|---|---|---|---|
| maintenance_id | str | Y | MNT-2026-NNNNNN | - | PK | ordered by actual_start_utc |
| plant_id | str | Y | - | - | - | FK Plant.plant_id |
| machine_id | str | Y | - | - | - | FK Machine.machine_id |
| event_type | enum | Y | PREVENTIVE,CORRECTIVE | - | - | - |
| reason_code | enum | Y | SCHEDULED_SERVICE,STANDBY_CONTROL_FAULT,COMPONENT_WEAR | - | - | - |
| scheduled_start_utc | datetime | Y | - | UTC | - | <= actual_start_utc |
| actual_start_utc | datetime | Y | - | UTC | - | < actual_end_utc |
| actual_end_utc | datetime | Y | - | UTC | - | - |
| status | enum | Y | COMPLETED | - | - | must equal last StatusHistory.to_state |

## Recommendation (`recommendation.csv`, source table)

| field | type | req | allowed values | unit | key | validation rule |
|---|---|---|---|---|---|---|
| recommendation_id | str | Y | REC-2026-NNNNNN | - | PK | ordered by created_at_utc |
| plant_id | str | Y | - | - | - | FK Plant.plant_id |
| meter_id | str | Y | - | - | - | FK Meter.meter_id; evidence meter |
| machine_id | str | N | - | - | - | FK Machine.machine_id; null for plant-level peak demand |
| rec_type | enum | Y | REDUCE_IDLE_LOAD,INVESTIGATE_INTENSITY_SHIFT,STAGGER_PEAK_STARTUPS | - | - | - |
| rule_id | str | Y | - | - | - | detector rule that produced it (R-IDLE-1, R-INT-1, R-PEAK-1) |
| created_at_utc | datetime | Y | - | UTC | - | >= evidence_end_utc |
| evidence_start_utc | datetime | Y | - | UTC | - | < evidence_end_utc |
| evidence_end_utc | datetime | Y | - | UTC | - | - |
| baseline_value | float | Y | >0 | see value_unit | - | measured baseline from the baseline window |
| observed_value | float | Y | >baseline_value | see value_unit | - | measured value in evidence window |
| value_unit | enum | Y | kW,kWh/unit | - | - | - |
| expected_savings_kwh | float | N | >=0 | kWh | - | null for peak-demand recs; (observed-baseline) x exposure over savings horizon |
| expected_savings_kw | float | N | >=0 | kW | - | only for peak-demand recs |
| expected_savings_cost | float | Y | >0 | currency | - | savings x tariff rate or demand charge |
| currency | enum | Y | USD,EUR | - | - | plant currency |
| savings_horizon_days | int | Y | 30 | days | - | - |
| status | enum | Y | OPEN,ACKNOWLEDGED,IMPLEMENTED | - | - | must equal last StatusHistory.to_state |

## StatusHistory (`status_history.csv`, source table)

| field | type | req | allowed values | unit | key | validation rule |
|---|---|---|---|---|---|---|
| history_id | str | Y | HST-2026-NNNNNN | - | PK | ordered by changed_at_utc |
| entity_type | enum | Y | ProductionBatch,MaintenanceEvent,Recommendation | - | - | polymorphic reference; entity_id validated per type |
| entity_id | str | Y | - | - | - | ID in the table named by entity_type |
| from_state | str | N | - | - | - | null on creation; must equal previous to_state |
| to_state | str | Y | - | - | - | valid lifecycle transition |
| changed_at_utc | datetime | Y | - | UTC | - | non-decreasing per entity |

## MachineStatePeriod (`machine_state_period.csv`, source table)

| field | type | req | allowed values | unit | key | validation rule |
|---|---|---|---|---|---|---|
| period_id | str | Y | SPD-<machine_id>-NNNNN | - | PK | - |
| machine_id | str | Y | - | - | - | FK Machine.machine_id |
| state | enum | Y | RUN,IDLE,STANDBY | - | - | RUN = batch executing; IDLE = working shift, no batch; STANDBY = outside working shifts |
| start_utc | datetime | Y | - | UTC | - | < end_utc |
| end_utc | datetime | Y | - | UTC | - | periods per machine are contiguous |
| batch_id | str | N | - | - | - | FK ProductionBatch.batch_id; set only when state = RUN |

## ReadingCost (`reading_cost.csv`, derived table (computed only from source tables))

| field | type | req | allowed values | unit | key | validation rule |
|---|---|---|---|---|---|---|
| reading_id | str | Y | - | - | PK | FK EnergyReading.reading_id; first transmission rows only |
| tariff_id | str | Y | - | - | - | FK Tariff.tariff_id; plant-local time, day type and effective date select the tariff |
| tou_band | enum | Y | OFFPEAK,SHOULDER,PEAK | - | - | - |
| rate_per_kwh | float | Y | >0 | currency/kWh | - | - |
| energy_kwh_clean | float | Y | >=0 | kWh | - | demand_kw_avg / 4 (repairs kW/kWh confusion) |
| cost | float | Y | >=0 | currency | - | energy_kwh_clean x rate_per_kwh |

## DailyPlantSummary (`daily_plant_summary.csv`, derived table (computed only from source tables))

| field | type | req | allowed values | unit | key | validation rule |
|---|---|---|---|---|---|---|
| summary_id | str | Y | DSUM-<plant>-YYYYMMDD | - | PK | - |
| plant_id | str | Y | - | - | - | FK Plant.plant_id |
| summary_date | date | Y | - | - | - | plant-local date |
| main_kwh | float | Y | >=0 | kWh | - | sum of clean main-meter interval energy |
| submeter_kwh | float | Y | >=0 | kWh | - | sum of clean submeter interval energy |
| unmetered_kwh | float | N | >=0 | kWh | - | main - submeters (lighting/HVAC); null when GAP_AFFECTED |
| units_produced | int | Y | >=0 | units | - | batches starting that local date |
| energy_intensity_kwh_per_unit | float | N | >0 | kWh/unit | - | main_kwh / units_produced; null if no units or GAP_AFFECTED |
| energy_cost | float | Y | >=0 | currency | - | sum of ReadingCost.cost for main meter |
| peak_kw | float | Y | >=0 | kW | - | max main demand_kw_avg of the day |
| missing_intervals | int | Y | >=0 | intervals | - | missing readings across the plant meters |
| reconcile_status | enum | Y | OK,GAP_AFFECTED | - | - | GAP_AFFECTED if any plant meter has missing intervals |

## BatchEnergy (`batch_energy.csv`, derived table (computed only from source tables))

| field | type | req | allowed values | unit | key | validation rule |
|---|---|---|---|---|---|---|
| batch_id | str | Y | - | - | PK | FK ProductionBatch.batch_id |
| machine_id | str | Y | - | - | - | FK Machine.machine_id |
| meter_id | str | Y | - | - | - | FK Meter.meter_id; DIRECT_SUB meter of the machine |
| energy_kwh | float | Y | >=0 | kWh | - | clean submeter energy over batch intervals |
| coverage_ratio | float | Y | 0..1 | - | - | share of batch intervals with a reading |
| energy_cost | float | Y | >=0 | currency | - | sum of interval energy x applicable rate |
| intensity_kwh_per_unit | float | N | >0 | kWh/unit | - | energy / units_produced; null if coverage < 1 or no units |
| baseline_intensity | float | N | >0 | kWh/unit | - | machine median of complete COMPLETED batches in baseline window |
| intensity_ratio | float | N | >0 | - | - | intensity / baseline_intensity |

## MonthlyDemand (`monthly_demand.csv`, derived table (computed only from source tables))

| field | type | req | allowed values | unit | key | validation rule |
|---|---|---|---|---|---|---|
| demand_id | str | Y | MDEM-<plant>-YYYYMM | - | PK | - |
| plant_id | str | Y | - | - | - | FK Plant.plant_id |
| month | str | Y | YYYY-MM | - | - | plant-local month |
| peak_kw | float | Y | >0 | kW | - | max main demand_kw_avg inside PEAK tariff band |
| peak_ts_utc | datetime | Y | - | UTC | - | interval start of the maximum |
| p95_peak_band_kw | float | Y | >0 | kW | - | 95th percentile of PEAK-band main demand |
| demand_charge_per_kw | float | Y | >=0 | currency/kW | - | from tariff valid at peak_ts_utc |
| demand_charge | float | Y | >=0 | currency | - | peak_kw x demand_charge_per_kw |
