# Validation summary

154/154 checks passed (28 foreign keys checked). Ground truth rows: 143.

| check | status | detail |
|---|---|---|
| columns match dictionary: Plant | PASS |  |
| PK unique: Plant | PASS | 2 rows |
| enum Plant.currency | PASS | [] |
| enum Plant.status | PASS | [] |
| columns match dictionary: Meter | PASS |  |
| PK unique: Meter | PASS | 20 rows |
| enum Meter.meter_type | PASS | [] |
| enum Meter.energy_unit | PASS | [] |
| enum Meter.demand_unit | PASS | [] |
| enum Meter.status | PASS | [] |
| columns match dictionary: Machine | PASS |  |
| PK unique: Machine | PASS | 18 rows |
| enum Machine.machine_type | PASS | [] |
| enum Machine.status | PASS | [] |
| columns match dictionary: MachineMeterAssignment | PASS |  |
| PK unique: MachineMeterAssignment | PASS | 36 rows |
| enum MachineMeterAssignment.relation | PASS | [] |
| columns match dictionary: Shift | PASS |  |
| PK unique: Shift | PASS | 542 rows |
| enum Shift.shift_code | PASS | [] |
| columns match dictionary: TariffCalendar | PASS |  |
| PK unique: TariffCalendar | PASS | 182 rows |
| enum TariffCalendar.day_type | PASS | [] |
| columns match dictionary: Tariff | PASS |  |
| PK unique: Tariff | PASS | 24 rows |
| enum Tariff.day_type | PASS | [] |
| enum Tariff.tou_band | PASS | [] |
| enum Tariff.currency | PASS | [] |
| columns match dictionary: WeatherObservation | PASS |  |
| PK unique: WeatherObservation | PASS | 4320 rows |
| enum WeatherObservation.source | PASS | [] |
| columns match dictionary: ProductionBatch | PASS |  |
| PK unique: ProductionBatch | PASS | 2000 rows |
| enum ProductionBatch.product_code | PASS | [] |
| enum ProductionBatch.status | PASS | [] |
| columns match dictionary: EnergyReading | PASS |  |
| PK unique: EnergyReading | PASS | 172103 rows |
| columns match dictionary: MaintenanceEvent | PASS |  |
| PK unique: MaintenanceEvent | PASS | 25 rows |
| enum MaintenanceEvent.event_type | PASS | [] |
| enum MaintenanceEvent.reason_code | PASS | [] |
| enum MaintenanceEvent.status | PASS | [] |
| columns match dictionary: Recommendation | PASS |  |
| PK unique: Recommendation | PASS | 11 rows |
| enum Recommendation.rec_type | PASS | [] |
| enum Recommendation.value_unit | PASS | [] |
| enum Recommendation.currency | PASS | [] |
| enum Recommendation.status | PASS | [] |
| columns match dictionary: StatusHistory | PASS |  |
| PK unique: StatusHistory | PASS | 6104 rows |
| enum StatusHistory.entity_type | PASS | [] |
| columns match dictionary: MachineStatePeriod | PASS |  |
| PK unique: MachineStatePeriod | PASS | 6514 rows |
| enum MachineStatePeriod.state | PASS | [] |
| columns match dictionary: ReadingCost | PASS |  |
| PK unique: ReadingCost | PASS | 172073 rows |
| enum ReadingCost.tou_band | PASS | [] |
| columns match dictionary: DailyPlantSummary | PASS |  |
| PK unique: DailyPlantSummary | PASS | 180 rows |
| enum DailyPlantSummary.reconcile_status | PASS | [] |
| columns match dictionary: BatchEnergy | PASS |  |
| PK unique: BatchEnergy | PASS | 2000 rows |
| columns match dictionary: MonthlyDemand | PASS |  |
| PK unique: MonthlyDemand | PASS | 6 rows |
| required fields non-null (all tables) | PASS |  |
| FK Meter.plant_id -> Plant.plant_id | PASS | 0 |
| FK Meter.parent_meter_id -> Meter.meter_id | PASS | 0 |
| FK Machine.plant_id -> Plant.plant_id | PASS | 0 |
| FK MachineMeterAssignment.machine_id -> Machine.machine_id | PASS | 0 |
| FK MachineMeterAssignment.meter_id -> Meter.meter_id | PASS | 0 |
| FK Shift.plant_id -> Plant.plant_id | PASS | 0 |
| FK TariffCalendar.plant_id -> Plant.plant_id | PASS | 0 |
| FK Tariff.plant_id -> Plant.plant_id | PASS | 0 |
| FK WeatherObservation.plant_id -> Plant.plant_id | PASS | 0 |
| FK ProductionBatch.plant_id -> Plant.plant_id | PASS | 0 |
| FK ProductionBatch.machine_id -> Machine.machine_id | PASS | 0 |
| FK ProductionBatch.shift_id -> Shift.shift_id | PASS | 0 |
| FK EnergyReading.meter_id -> Meter.meter_id | PASS | 0 |
| FK EnergyReading.machine_id -> Machine.machine_id | PASS | 0 |
| FK MaintenanceEvent.plant_id -> Plant.plant_id | PASS | 0 |
| FK MaintenanceEvent.machine_id -> Machine.machine_id | PASS | 0 |
| FK Recommendation.plant_id -> Plant.plant_id | PASS | 0 |
| FK Recommendation.meter_id -> Meter.meter_id | PASS | 0 |
| FK Recommendation.machine_id -> Machine.machine_id | PASS | 0 |
| FK MachineStatePeriod.machine_id -> Machine.machine_id | PASS | 0 |
| FK MachineStatePeriod.batch_id -> ProductionBatch.batch_id | PASS | 0 |
| FK ReadingCost.reading_id -> EnergyReading.reading_id | PASS | 0 |
| FK ReadingCost.tariff_id -> Tariff.tariff_id | PASS | 0 |
| FK DailyPlantSummary.plant_id -> Plant.plant_id | PASS | 0 |
| FK BatchEnergy.batch_id -> ProductionBatch.batch_id | PASS | 0 |
| FK BatchEnergy.machine_id -> Machine.machine_id | PASS | 0 |
| FK BatchEnergy.meter_id -> Meter.meter_id | PASS | 0 |
| FK MonthlyDemand.plant_id -> Plant.plant_id | PASS | 0 |
| StatusHistory polymorphic FK -> ProductionBatch | PASS |  |
| StatusHistory polymorphic FK -> MaintenanceEvent | PASS |  |
| StatusHistory polymorphic FK -> Recommendation | PASS |  |
| ID patterns | PASS |  |
| one MAIN meter per plant | PASS |  |
| SUB meters parent is MAIN of same plant | PASS |  |
| every machine has DIRECT_SUB + INDIRECT_MAIN | PASS |  |
| bridge: machine and meter in same plant | PASS |  |
| meters = machines + plants (sub per machine) | PASS |  |
| interval = 15 min | PASS |  |
| demand_peak >= demand_avg; values non-negative | PASS |  |
| duplicate natural keys == ground truth | PASS | 30 found |
| missing intervals == ground-truth gaps | PASS | 727 missing |
| kW/kWh confusion detected == ground truth | PASS | 25 detected |
| confused rows are 4x overstated | PASS |  |
| meter register vs interval sum mismatches == ground truth | PASS | 3 detected |
| register delta after gap >= interval energy (lost energy kept in register) | PASS |  |
| register deltas reconcile on all unaffected consecutive rows | PASS | 171986 rows |
| machine outside meter hierarchy == ground truth | PASS | 25 detected |
| MAIN meter readings carry no machine_id | PASS |  |
| energy totals reconcile: main > sum(submeters) in every interval; overall unmetered share 10-25% | PASS | 16576 fully observed intervals, overall unmetered 15.8% (interval range 5.3%-57.9%; higher at night/Sundays when machines are in standby) |
| tariff windows tile 24h without overlap per plant/day type/period | PASS |  |
| tariff timezone mismatch == ground truth | PASS | 1 rows |
| ReadingCost covers each first-transmission reading once | PASS |  |
| cost uses correct tariff interval (independent tz recompute) | PASS | 0 mismatches |
| cost = clean energy x rate; clean energy = kW/4 | PASS |  |
| rate matches tariff row | PASS |  |
| shifts are 8h, ordered | PASS |  |
| batch start inside a working shift of same plant | PASS |  |
| batch date ordering (start < end <= planned_end) | PASS |  |
| units_produced <= units_planned | PASS |  |
| no overlapping batches per machine | PASS |  |
| batch machine in batch plant | PASS |  |
| batch ids ordered by start time | PASS |  |
| aborted batches end early | PASS |  |
| lifecycle transitions valid | PASS |  |
| history chains consistent (from == previous to) | PASS |  |
| history timestamps non-decreasing per entity | PASS |  |
| ProductionBatch.status equals last history state | PASS |  |
| MaintenanceEvent.status equals last history state | PASS |  |
| Recommendation.status equals last history state | PASS |  |
| maintenance date ordering | PASS |  |
| state periods contiguous per machine | PASS |  |
| RUN periods equal their batch window | PASS |  |
| batch_id set only for RUN | PASS |  |
| daily main_kwh equals sum of ReadingCost on main meter | PASS |  |
| daily cost equals sum of ReadingCost (main meter) | PASS |  |
| daily units equal batch units | PASS |  |
| daily intensity = main kWh / units (normalised by output) | PASS |  |
| BatchEnergy intensity = energy / units on full-coverage batches | PASS |  |
| demand charge = peak_kw x tariff demand charge | PASS |  |
| recommendations cite measurable baseline and expected savings | PASS |  |
| recommendation evidence precedes creation | PASS |  |
| REDUCE_IDLE_LOAD: recommended machines == ground-truth machines | PASS | got ['MCH-P01-001', 'MCH-P01-003', 'MCH-P01-006', 'MCH-P02-003'] want ['MCH-P01-001', 'MCH-P01-003', 'MCH-P01-006', 'MCH-P02-003'] |
| INVESTIGATE_INTENSITY_SHIFT: recommended machines == ground-truth machines | PASS | got ['MCH-P01-005', 'MCH-P01-009', 'MCH-P02-002'] want ['MCH-P01-005', 'MCH-P01-009', 'MCH-P02-002'] |
| every peak-demand recommendation sits in a plant-month with an injected spike | PASS | [('P01', '2026-08'), ('P02', '2026-07'), ('P02', '2026-08'), ('P02', '2026-09')] |
| weather hourly, one row per plant-hour; plausible range | PASS |  |
| weather cadence is exactly 1h | PASS |  |
| no ground-truth columns in input tables | PASS |  |
| ground truth file has documented columns | PASS |  |
| ground-truth ids not embedded in input data | PASS |  |

## Ground-truth anomaly counts

- DUPLICATE_READING: 30
- ENERGY_INTENSITY_SHIFT: 3
- HIGH_IDLE_CONSUMPTION: 4
- KW_KWH_CONFUSION: 25
- MACHINE_OUTSIDE_METER_HIERARCHY: 25
- METER_GAP: 39
- METER_TOTAL_MISMATCH: 3
- PEAK_DEMAND_SPIKE: 13
- TARIFF_TIMEZONE_MISMATCH: 1
