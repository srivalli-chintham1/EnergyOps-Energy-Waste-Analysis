#!/usr/bin/env python3
"""Synthetic industrial energy dataset generator (meters, machines, batches, tariffs, weather).

Same code produces starter and full scale; only parameters differ. Fully deterministic for a given
seed + parameters (single numpy Generator, fixed draw order, no wall-clock values in outputs).
Ground truth is written to a separate folder and never referenced by input tables.
"""
import argparse, gzip, hashlib, json, os, sqlite3, sys
import numpy as np
import pandas as pd

Q = 96  # 15-minute intervals per day
PLANTS = [  # id, name, tz, lat, lon, currency
    ("P01", "Northfield Stamping", "America/Chicago", 41.88, -87.63, "USD"),
    ("P02", "Rheinwerk Plastics", "Europe/Berlin", 52.52, 13.40, "EUR"),
]
HOLIDAYS = {("P01", "2026-07-03"): "Independence Day (observed)", ("P01", "2026-09-07"): "Labor Day"}
# type: rated_lo, rated_hi, idle_frac_lo, idle_frac_hi, uph_lo, uph_hi, weather_sensitive
MTYPES = {
    "PRESS": (80, 200, .10, .18, 200, 500, 0), "INJECTION_MOLDER": (40, 120, .15, .25, 120, 300, 0),
    "CNC_MILL": (15, 45, .12, .20, 20, 40, 0), "COMPRESSOR": (30, 90, .22, .30, 400, 800, 1),
    "OVEN": (60, 150, .22, .30, 50, 120, 0), "CHILLER": (50, 130, .20, .28, 300, 600, 1),
    "CONVEYOR": (5, 15, .15, .25, 600, 1200, 0)}
TYPE_ORDER = list(MTYPES)
TARIFF_RATES = {"P01": (0.062, 0.095, 0.158, 14.5), "P02": (0.110, 0.170, 0.260, 9.8)}
WEEKDAY_WIN = [("OFFPEAK", "22:00", "06:00"), ("SHOULDER", "06:00", "14:00"),
               ("PEAK", "14:00", "20:00"), ("SHOULDER", "20:00", "22:00")]
WEEKEND_WIN = [("OFFPEAK", "18:00", "10:00"), ("SHOULDER", "10:00", "18:00")]
PRODUCTS = ["PRD-A", "PRD-B", "PRD-C", "PRD-D"]

# entity|field|type|required|allowed|unit|key|rule   ('-' = none; FK given as "FK Entity.field")
DD_TEXT = """
Plant|plant_id|str|Y|P<nn>|-|PK|pattern P\\d{2}; immutable
Plant|plant_name|str|Y|-|-|-|non-empty
Plant|timezone|str|Y|IANA zone|-|-|valid zone; tariff windows are interpreted in this zone
Plant|latitude|float|Y|-90..90|deg|-|range check
Plant|longitude|float|Y|-180..180|deg|-|range check
Plant|currency|enum|Y|USD,EUR|-|-|one currency per plant
Plant|status|enum|Y|ACTIVE,INACTIVE|-|-|lifecycle state
Plant|commissioned_date|date|Y|-|-|-|<= first reading date
Meter|meter_id|str|Y|MTR-<plant>-NNN|-|PK|zero-padded counter per plant; 001 is the MAIN meter
Meter|plant_id|str|Y|-|-|-|FK Plant.plant_id
Meter|meter_type|enum|Y|MAIN,SUB|-|-|exactly one MAIN per plant
Meter|parent_meter_id|str|N|-|-|-|FK Meter.meter_id; null for MAIN; SUB parent is the MAIN of the same plant
Meter|energy_unit|enum|Y|kWh|-|-|interval energy unit
Meter|demand_unit|enum|Y|kW|-|-|demand unit; kW = kWh x 60 / sampling_minutes
Meter|sampling_minutes|int|Y|15|min|-|equals interval length of readings
Meter|install_date|date|Y|-|-|-|<= first reading date
Meter|register_start_kwh|float|Y|>=0|kWh|-|cumulative register value at start of first interval
Meter|status|enum|Y|ACTIVE,INACTIVE|-|-|lifecycle state
Machine|machine_id|str|Y|MCH-<plant>-NNN|-|PK|zero-padded counter per plant
Machine|plant_id|str|Y|-|-|-|FK Plant.plant_id
Machine|machine_type|enum|Y|PRESS,INJECTION_MOLDER,CNC_MILL,COMPRESSOR,OVEN,CHILLER,CONVEYOR|-|-|-
Machine|rated_kw|float|Y|>0|kW|-|full-load power
Machine|idle_kw|float|Y|>0|kW|-|nominal idle draw; < 0.5 x rated_kw
Machine|standby_kw|float|Y|>0|kW|-|nominal draw outside working shifts
Machine|units_per_hour|float|Y|>0|units/h|-|nominal throughput
Machine|weather_sensitive|bool|Y|0,1|-|-|1 = load scales with outdoor temperature above 22 C
Machine|commissioned_date|date|Y|-|-|-|<= first batch
Machine|status|enum|Y|ACTIVE,INACTIVE|-|-|lifecycle state
MachineMeterAssignment|assignment_id|str|Y|MMA-<plant>-NNN|-|PK|zero-padded per plant
MachineMeterAssignment|machine_id|str|Y|-|-|-|FK Machine.machine_id
MachineMeterAssignment|meter_id|str|Y|-|-|-|FK Meter.meter_id; same plant as machine
MachineMeterAssignment|relation|enum|Y|DIRECT_SUB,INDIRECT_MAIN|-|-|N:M bridge; each machine has one DIRECT_SUB and one INDIRECT_MAIN row
MachineMeterAssignment|effective_from|date|Y|-|-|-|-
MachineMeterAssignment|effective_to|date|N|-|-|-|null = open; >= effective_from
Shift|shift_id|str|Y|SHF-<plant>-YYYYMMDD-<A/B/C>|-|PK|one row per plant, local date, shift code
Shift|plant_id|str|Y|-|-|-|FK Plant.plant_id
Shift|shift_date|date|Y|-|-|-|local date the shift starts
Shift|shift_code|enum|Y|A,B,C|-|-|A 06-14, B 14-22, C 22-06 (local)
Shift|start_utc|datetime|Y|-|UTC|-|< end_utc
Shift|end_utc|datetime|Y|-|UTC|-|8 hours after start
Shift|is_working|bool|Y|0,1|-|-|A/B on weekdays, A on Saturdays, none on Sundays/holidays, C never
TariffCalendar|calendar_id|str|Y|TCAL-<plant>-YYYYMMDD|-|PK|-
TariffCalendar|plant_id|str|Y|-|-|-|FK Plant.plant_id
TariffCalendar|calendar_date|date|Y|-|-|-|local date
TariffCalendar|day_type|enum|Y|WEEKDAY,WEEKEND|-|-|weekends and holidays are WEEKEND
TariffCalendar|holiday_name|str|N|-|-|-|set only for holidays
Tariff|tariff_id|str|Y|TAR-2026-NNN|-|PK|zero-padded counter
Tariff|plant_id|str|Y|-|-|-|FK Plant.plant_id
Tariff|day_type|enum|Y|WEEKDAY,WEEKEND|-|-|-
Tariff|tou_band|enum|Y|OFFPEAK,SHOULDER,PEAK|-|-|-
Tariff|window_start_local|str|Y|HH:MM|-|-|local clock; window wraps midnight if start > end
Tariff|window_end_local|str|Y|HH:MM|-|-|exclusive
Tariff|timezone|str|Y|IANA zone|-|-|must equal the plant timezone
Tariff|rate_per_kwh|float|Y|>0|currency/kWh|-|-
Tariff|demand_charge_per_kw|float|Y|>=0|currency/kW-month|-|> 0 only for PEAK band
Tariff|currency|enum|Y|USD,EUR|-|-|equals plant currency
Tariff|effective_from|date|Y|-|-|-|windows of one plant+day_type+effective period tile 24 h with no overlap
Tariff|effective_to|date|N|-|-|-|null = open
WeatherObservation|weather_id|str|Y|WX-<plant>-YYYYMMDDHH|-|PK|hour is UTC
WeatherObservation|plant_id|str|Y|-|-|-|FK Plant.plant_id
WeatherObservation|observed_at_utc|datetime|Y|-|UTC|-|hourly
WeatherObservation|temperature_c|float|Y|-30..50|C|-|-
WeatherObservation|relative_humidity_pct|float|Y|0..100|%|-|-
WeatherObservation|source|enum|Y|SYNTHETIC|-|-|no external data used
ProductionBatch|batch_id|str|Y|BATCH-2026-NNNNNN|-|PK|ordered by start_utc then machine_id
ProductionBatch|plant_id|str|Y|-|-|-|FK Plant.plant_id
ProductionBatch|machine_id|str|Y|-|-|-|FK Machine.machine_id; same plant; no overlapping batches per machine
ProductionBatch|shift_id|str|Y|-|-|-|FK Shift.shift_id; shift containing start_utc, must be working
ProductionBatch|product_code|enum|Y|PRD-A,PRD-B,PRD-C,PRD-D|-|-|-
ProductionBatch|start_utc|datetime|Y|-|UTC|-|15-minute aligned
ProductionBatch|planned_end_utc|datetime|Y|-|UTC|-|> start_utc
ProductionBatch|end_utc|datetime|Y|-|UTC|-|actual end; <= planned_end_utc (earlier if ABORTED)
ProductionBatch|units_planned|int|Y|>0|units|-|-
ProductionBatch|units_produced|int|Y|>=0|units|-|<= units_planned
ProductionBatch|status|enum|Y|COMPLETED,ABORTED|-|-|must equal last StatusHistory.to_state
EnergyReading|reading_id|str|Y|ENG-<meter_id>-<YYYYMMDDTHHMMZ>[-R2]|-|PK|-R2 suffix = retransmitted copy added by the ingest gateway
EnergyReading|meter_id|str|Y|-|-|-|FK Meter.meter_id
EnergyReading|interval_start_utc|datetime|Y|-|UTC|-|15-minute aligned; natural key with meter_id + ingest_seq
EnergyReading|interval_end_utc|datetime|Y|-|UTC|-|start + 15 min
EnergyReading|energy_kwh|float|Y|>=0|kWh|-|interval energy; expected = demand_kw_avg / 4
EnergyReading|demand_kw_avg|float|Y|>=0|kW|-|average demand over the interval
EnergyReading|demand_kw_peak|float|Y|>=demand_kw_avg|kW|-|maximum demand within the interval
EnergyReading|register_kwh|float|Y|>=0|kWh|-|cumulative register at interval end; delta = interval energy
EnergyReading|machine_id|str|N|-|-|-|FK Machine.machine_id; machine behind a SUB meter; null on MAIN meters
EnergyReading|ingest_seq|int|Y|1,2|-|-|2 = retransmission
MaintenanceEvent|maintenance_id|str|Y|MNT-2026-NNNNNN|-|PK|ordered by actual_start_utc
MaintenanceEvent|plant_id|str|Y|-|-|-|FK Plant.plant_id
MaintenanceEvent|machine_id|str|Y|-|-|-|FK Machine.machine_id
MaintenanceEvent|event_type|enum|Y|PREVENTIVE,CORRECTIVE|-|-|-
MaintenanceEvent|reason_code|enum|Y|SCHEDULED_SERVICE,STANDBY_CONTROL_FAULT,COMPONENT_WEAR|-|-|-
MaintenanceEvent|scheduled_start_utc|datetime|Y|-|UTC|-|<= actual_start_utc
MaintenanceEvent|actual_start_utc|datetime|Y|-|UTC|-|< actual_end_utc
MaintenanceEvent|actual_end_utc|datetime|Y|-|UTC|-|-
MaintenanceEvent|status|enum|Y|COMPLETED|-|-|must equal last StatusHistory.to_state
Recommendation|recommendation_id|str|Y|REC-2026-NNNNNN|-|PK|ordered by created_at_utc
Recommendation|plant_id|str|Y|-|-|-|FK Plant.plant_id
Recommendation|meter_id|str|Y|-|-|-|FK Meter.meter_id; evidence meter
Recommendation|machine_id|str|N|-|-|-|FK Machine.machine_id; null for plant-level peak demand
Recommendation|rec_type|enum|Y|REDUCE_IDLE_LOAD,INVESTIGATE_INTENSITY_SHIFT,STAGGER_PEAK_STARTUPS|-|-|-
Recommendation|rule_id|str|Y|-|-|-|detector rule that produced it (R-IDLE-1, R-INT-1, R-PEAK-1)
Recommendation|created_at_utc|datetime|Y|-|UTC|-|>= evidence_end_utc
Recommendation|evidence_start_utc|datetime|Y|-|UTC|-|< evidence_end_utc
Recommendation|evidence_end_utc|datetime|Y|-|UTC|-|-
Recommendation|baseline_value|float|Y|>0|see value_unit|-|measured baseline from the baseline window
Recommendation|observed_value|float|Y|>baseline_value|see value_unit|-|measured value in evidence window
Recommendation|value_unit|enum|Y|kW,kWh/unit|-|-|-
Recommendation|expected_savings_kwh|float|N|>=0|kWh|-|null for peak-demand recs; (observed-baseline) x exposure over savings horizon
Recommendation|expected_savings_kw|float|N|>=0|kW|-|only for peak-demand recs
Recommendation|expected_savings_cost|float|Y|>0|currency|-|savings x tariff rate or demand charge
Recommendation|currency|enum|Y|USD,EUR|-|-|plant currency
Recommendation|savings_horizon_days|int|Y|30|days|-|-
Recommendation|status|enum|Y|OPEN,ACKNOWLEDGED,IMPLEMENTED|-|-|must equal last StatusHistory.to_state
StatusHistory|history_id|str|Y|HST-2026-NNNNNN|-|PK|ordered by changed_at_utc
StatusHistory|entity_type|enum|Y|ProductionBatch,MaintenanceEvent,Recommendation|-|-|polymorphic reference; entity_id validated per type
StatusHistory|entity_id|str|Y|-|-|-|ID in the table named by entity_type
StatusHistory|from_state|str|N|-|-|-|null on creation; must equal previous to_state
StatusHistory|to_state|str|Y|-|-|-|valid lifecycle transition
StatusHistory|changed_at_utc|datetime|Y|-|UTC|-|non-decreasing per entity
MachineStatePeriod|period_id|str|Y|SPD-<machine_id>-NNNNN|-|PK|-
MachineStatePeriod|machine_id|str|Y|-|-|-|FK Machine.machine_id
MachineStatePeriod|state|enum|Y|RUN,IDLE,STANDBY|-|-|RUN = batch executing; IDLE = working shift, no batch; STANDBY = outside working shifts
MachineStatePeriod|start_utc|datetime|Y|-|UTC|-|< end_utc
MachineStatePeriod|end_utc|datetime|Y|-|UTC|-|periods per machine are contiguous
MachineStatePeriod|batch_id|str|N|-|-|-|FK ProductionBatch.batch_id; set only when state = RUN
ReadingCost|reading_id|str|Y|-|-|PK|FK EnergyReading.reading_id; first transmission rows only
ReadingCost|tariff_id|str|Y|-|-|-|FK Tariff.tariff_id; plant-local time, day type and effective date select the tariff
ReadingCost|tou_band|enum|Y|OFFPEAK,SHOULDER,PEAK|-|-|-
ReadingCost|rate_per_kwh|float|Y|>0|currency/kWh|-|-
ReadingCost|energy_kwh_clean|float|Y|>=0|kWh|-|demand_kw_avg / 4 (repairs kW/kWh confusion)
ReadingCost|cost|float|Y|>=0|currency|-|energy_kwh_clean x rate_per_kwh
DailyPlantSummary|summary_id|str|Y|DSUM-<plant>-YYYYMMDD|-|PK|-
DailyPlantSummary|plant_id|str|Y|-|-|-|FK Plant.plant_id
DailyPlantSummary|summary_date|date|Y|-|-|-|plant-local date
DailyPlantSummary|main_kwh|float|Y|>=0|kWh|-|sum of clean main-meter interval energy
DailyPlantSummary|submeter_kwh|float|Y|>=0|kWh|-|sum of clean submeter interval energy
DailyPlantSummary|unmetered_kwh|float|N|>=0|kWh|-|main - submeters (lighting/HVAC); null when GAP_AFFECTED
DailyPlantSummary|units_produced|int|Y|>=0|units|-|batches starting that local date
DailyPlantSummary|energy_intensity_kwh_per_unit|float|N|>0|kWh/unit|-|main_kwh / units_produced; null if no units or GAP_AFFECTED
DailyPlantSummary|energy_cost|float|Y|>=0|currency|-|sum of ReadingCost.cost for main meter
DailyPlantSummary|peak_kw|float|Y|>=0|kW|-|max main demand_kw_avg of the day
DailyPlantSummary|missing_intervals|int|Y|>=0|intervals|-|missing readings across the plant meters
DailyPlantSummary|reconcile_status|enum|Y|OK,GAP_AFFECTED|-|-|GAP_AFFECTED if any plant meter has missing intervals
BatchEnergy|batch_id|str|Y|-|-|PK|FK ProductionBatch.batch_id
BatchEnergy|machine_id|str|Y|-|-|-|FK Machine.machine_id
BatchEnergy|meter_id|str|Y|-|-|-|FK Meter.meter_id; DIRECT_SUB meter of the machine
BatchEnergy|energy_kwh|float|Y|>=0|kWh|-|clean submeter energy over batch intervals
BatchEnergy|coverage_ratio|float|Y|0..1|-|-|share of batch intervals with a reading
BatchEnergy|energy_cost|float|Y|>=0|currency|-|sum of interval energy x applicable rate
BatchEnergy|intensity_kwh_per_unit|float|N|>0|kWh/unit|-|energy / units_produced; null if coverage < 1 or no units
BatchEnergy|baseline_intensity|float|N|>0|kWh/unit|-|machine median of complete COMPLETED batches in baseline window
BatchEnergy|intensity_ratio|float|N|>0|-|-|intensity / baseline_intensity
MonthlyDemand|demand_id|str|Y|MDEM-<plant>-YYYYMM|-|PK|-
MonthlyDemand|plant_id|str|Y|-|-|-|FK Plant.plant_id
MonthlyDemand|month|str|Y|YYYY-MM|-|-|plant-local month
MonthlyDemand|peak_kw|float|Y|>0|kW|-|max main demand_kw_avg inside PEAK tariff band
MonthlyDemand|peak_ts_utc|datetime|Y|-|UTC|-|interval start of the maximum
MonthlyDemand|p95_peak_band_kw|float|Y|>0|kW|-|95th percentile of PEAK-band main demand
MonthlyDemand|demand_charge_per_kw|float|Y|>=0|currency/kW|-|from tariff valid at peak_ts_utc
MonthlyDemand|demand_charge|float|Y|>=0|currency|-|peak_kw x demand_charge_per_kw
"""
ENTITY_ORDER = []
FILES = {"Plant": "plant", "Meter": "meter", "Machine": "machine", "MachineMeterAssignment": "machine_meter_assignment",
         "Shift": "shift", "TariffCalendar": "tariff_calendar", "Tariff": "tariff", "WeatherObservation": "weather_observation",
         "ProductionBatch": "production_batch", "EnergyReading": "energy_reading", "MaintenanceEvent": "maintenance_event",
         "Recommendation": "recommendation", "StatusHistory": "status_history", "MachineStatePeriod": "machine_state_period",
         "ReadingCost": "reading_cost", "DailyPlantSummary": "daily_plant_summary", "BatchEnergy": "batch_energy",
         "MonthlyDemand": "monthly_demand"}
LARGE = {"EnergyReading", "ReadingCost"}  # not duplicated as JSON
DERIVED = {"ReadingCost", "DailyPlantSummary", "BatchEnergy", "MonthlyDemand"}
GT_COLS = ["gt_id", "issue_type", "entity_type", "entity_id", "plant_id", "start_utc", "end_utc",
           "magnitude", "magnitude_unit", "expected_decision", "detail"]


def parse_dd():
    dd = {}
    for ln in DD_TEXT.strip().splitlines():
        p = [("" if x.strip() == "-" else x.strip()) for x in ln.split("|")]
        assert len(p) == 8, ln
        dd.setdefault(p[0], []).append(dict(zip(["entity", "field", "type", "required", "allowed", "unit", "key", "rule"], p)))
    return dd


DD = parse_dd()


def cols(entity):
    return [r["field"] for r in DD[entity]]


def ddl():
    out = ["-- Generated from the data dictionary. SQLite dialect.", "PRAGMA foreign_keys = ON;"]
    tmap = {"float": "REAL", "int": "INTEGER", "bool": "INTEGER"}
    for ent, rows in DD.items():
        lines = []
        for r in rows:
            lines.append(f'  {r["field"]} {tmap.get(r["type"], "TEXT")}{" NOT NULL" if r["required"] == "Y" else ""}')
        pk = [r["field"] for r in rows if r["key"] == "PK"]
        lines.append(f'  PRIMARY KEY ({", ".join(pk)})')
        for r in rows:
            if r["rule"].startswith("FK ") or "; FK " in r["rule"] or r["rule"].startswith("FK"):
                tgt = r["rule"].split("FK ", 1)[1].split(";")[0].strip().split(" ")[0]
                te, tf = tgt.split(".")
                if ent == "ReadingCost" and r["field"] == "reading_id":
                    pass
                lines.append(f'  FOREIGN KEY ({r["field"]}) REFERENCES {FILES[te]}({tf})')
        out.append(f"CREATE TABLE {FILES[ent]} (\n" + ",\n".join(lines) + "\n);")
    return "\n".join(out) + "\n"


def dd_markdown():
    s = ["# Data dictionary", "", "Generated from `generate.py` (single source of truth for schema, SQL DDL and validation).",
         "Key: PK = primary key; FK targets are given in the rule column. `-` = not applicable.", ""]
    for ent, rows in DD.items():
        kind = "derived table (computed only from source tables)" if ent in DERIVED else "source table"
        s += [f"## {ent} (`{FILES[ent]}.csv`, {kind})", "", "| field | type | req | allowed values | unit | key | validation rule |", "|---|---|---|---|---|---|---|"]
        for r in rows:
            s.append("| " + " | ".join((r[k] or "-").replace("|", "/") for k in ["field", "type", "required", "allowed", "unit", "key", "rule"]) + " |")
        s.append("")
    return "\n".join(s)


def l2u(naive_ts, tz):
    return pd.Timestamp(naive_ts).tz_localize(tz).tz_convert("UTC")


def fmt_df(df):
    df = df.copy()
    for c in df.columns:
        if isinstance(df[c].dtype, pd.DatetimeTZDtype):
            df[c] = df[c].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return df


def build(a):
    rng = np.random.default_rng(a.seed)
    start = pd.Timestamp(a.start)
    days, P = a.days, a.plants
    T = days * Q
    pl = PLANTS[:P]
    counts = [a.meters // P + (1 if i < a.meters % P else 0) for i in range(P)]
    assert min(counts) >= 2, "need >= 2 meters per plant (1 main + 1 sub)"
    gl = pd.date_range(start, periods=T, freq="15min")
    gu = [gl.tz_localize(p[2]).tz_convert("UTC") for p in pl]
    tsc = [g.strftime("%Y%m%dT%H%MZ").to_numpy() for g in gu]
    first_date = start.strftime("%Y-%m-%d")
    install = (start - pd.Timedelta(days=400)).strftime("%Y-%m-%d")

    # ---------------- master data ----------------
    plant = pd.DataFrame([dict(plant_id=p[0], plant_name=p[1], timezone=p[2], latitude=p[3], longitude=p[4], currency=p[5],
                               status="ACTIVE", commissioned_date="2019-04-01") for p in pl])
    meters, machines = [], []
    for pi, p in enumerate(pl):
        mid = f"MTR-{p[0]}-001"
        meters.append(dict(id=mid, pi=pi, type="MAIN", parent=None, machine=None))
        for j in range(counts[pi] - 1):
            mi = len(machines)
            tname = TYPE_ORDER[(j + 3 * pi) % len(TYPE_ORDER)]
            lo = MTYPES[tname]
            rated = round(float(rng.uniform(lo[0], lo[1])), 1)
            machines.append(dict(id=f"MCH-{p[0]}-{j + 1:03d}", pi=pi, type=tname, rated=rated,
                                 idle=round(rated * float(rng.uniform(lo[2], lo[3])), 2), stby=round(rated * 0.03, 2),
                                 uph=round(float(rng.uniform(lo[4], lo[5])), 1), ws=lo[6], meter=len(meters)))
            meters.append(dict(id=f"MTR-{p[0]}-{j + 2:03d}", pi=pi, type="SUB", parent=mid, machine=mi))
    M, Mt = len(machines), len(meters)
    main_of = {pi: next(i for i, m in enumerate(meters) if m["pi"] == pi and m["type"] == "MAIN") for pi in range(P)}
    meter_df = pd.DataFrame([dict(meter_id=m["id"], plant_id=pl[m["pi"]][0], meter_type=m["type"], parent_meter_id=m["parent"],
                                  energy_unit="kWh", demand_unit="kW", sampling_minutes=15, install_date=install,
                                  register_start_kwh=round(float(rng.uniform(1e5, 5e5)), 1), status="ACTIVE") for m in meters])
    reg0 = meter_df["register_start_kwh"].to_numpy()
    machine_df = pd.DataFrame([dict(machine_id=m["id"], plant_id=pl[m["pi"]][0], machine_type=m["type"], rated_kw=m["rated"],
                                    idle_kw=m["idle"], standby_kw=m["stby"], units_per_hour=m["uph"], weather_sensitive=m["ws"],
                                    commissioned_date="2020-01-15", status="ACTIVE") for m in machines])
    assign, cnt = [], {}
    for m in machines:
        pid = pl[m["pi"]][0]
        for rel, mt in (("DIRECT_SUB", meters[m["meter"]]), ("INDIRECT_MAIN", meters[main_of[m["pi"]]])):
            cnt[pid] = cnt.get(pid, 0) + 1
            assign.append(dict(assignment_id=f"MMA-{pid}-{cnt[pid]:03d}", machine_id=m["id"], meter_id=mt["id"], relation=rel,
                               effective_from="2020-01-15", effective_to=None))
    assign_df = pd.DataFrame(assign)
    rated = np.array([m["rated"] for m in machines]); idle_kw = np.array([m["idle"] for m in machines])
    stby = np.array([m["stby"] for m in machines]); uph = np.array([m["uph"] for m in machines])
    wsens = np.array([m["ws"] for m in machines]); mplant = np.array([m["pi"] for m in machines])

    # ---------------- calendar, shifts, tariffs ----------------
    cal, cal_rows, shift_rows = {}, [], []
    working = np.zeros((P, T), bool)
    dtarr = np.empty((P, T), dtype=object)
    for pi, p in enumerate(pl):
        for d in range(-1, days):
            date = start + pd.Timedelta(days=d)
            ds = date.strftime("%Y-%m-%d")
            hol = HOLIDAYS.get((p[0], ds))
            wd = date.weekday()
            dtype = "WEEKEND" if (wd >= 5 or hol) else "WEEKDAY"
            wA = (wd < 6) and not hol
            wB = (wd < 5) and not hol
            cal[(pi, d)] = (dtype, wA, wB)
            cal_rows.append(dict(calendar_id=f"TCAL-{p[0]}-{date:%Y%m%d}", plant_id=p[0], calendar_date=ds, day_type=dtype, holiday_name=hol))
            for code, h0, wk in (("A", 6, wA), ("B", 14, wB), ("C", 22, False)):
                if d == -1 and code != "C":
                    continue
                s_l = date + pd.Timedelta(hours=h0)
                shift_rows.append(dict(shift_id=f"SHF-{p[0]}-{date:%Y%m%d}-{code}", plant_id=p[0], shift_date=ds, shift_code=code,
                                       start_utc=l2u(s_l, p[2]), end_utc=l2u(s_l + pd.Timedelta(hours=8), p[2]), is_working=int(wk)))
                if wk and d >= 0:
                    working[pi, d * Q + h0 * 4: d * Q + h0 * 4 + 32] = True
            if d >= 0:
                dtarr[pi, d * Q:(d + 1) * Q] = dtype
    cal_df, shift_df = pd.DataFrame(cal_rows), pd.DataFrame(shift_rows)
    split = max(1, days // 2)
    periods = [(0, split - 1, 1.0), (split, None, 1.06)]
    tar_rows, tcount = [], 0
    for pi, p in enumerate(pl):
        r_off, r_sh, r_pk, dem = TARIFF_RATES[p[0]]
        for (ef, et, mult) in periods:
            for dtype, wins in (("WEEKDAY", WEEKDAY_WIN), ("WEEKEND", WEEKEND_WIN)):
                for band, s, e in wins:
                    tcount += 1
                    rate = {"OFFPEAK": r_off, "SHOULDER": r_sh, "PEAK": r_pk}[band]
                    tz_label = p[2]
                    if p[0] == "P02" and ef == split and dtype == "WEEKDAY" and band == "PEAK":
                        tz_label = "UTC"  # injected: tariff timezone mismatch (labelled in ground truth)
                    tar_rows.append(dict(tariff_id=f"TAR-2026-{tcount:03d}", plant_id=p[0], day_type=dtype, tou_band=band,
                                         window_start_local=s, window_end_local=e, timezone=tz_label, rate_per_kwh=round(rate * mult, 4),
                                         demand_charge_per_kw=round(dem * mult, 2) if band == "PEAK" else 0.0, currency=p[5],
                                         effective_from=(start + pd.Timedelta(days=ef)).strftime("%Y-%m-%d"),
                                         effective_to=None if et is None else (start + pd.Timedelta(days=et)).strftime("%Y-%m-%d"),
                                         _ef=ef, _et=days + 10 if et is None else et))
    tar_df = pd.DataFrame(tar_rows)
    lmin = (gl.hour * 60 + gl.minute).to_numpy(); dayidx = np.arange(T) // Q
    rate = np.zeros((P, T)); dcr = np.zeros((P, T)); band = np.empty((P, T), dtype=object); tid = np.empty((P, T), dtype=object)
    for t in tar_rows:
        pi = [p[0] for p in pl].index(t["plant_id"])
        s = int(t["window_start_local"][:2]) * 60 + int(t["window_start_local"][3:]); e = int(t["window_end_local"][:2]) * 60 + int(t["window_end_local"][3:])
        inwin = (lmin >= s) & (lmin < e) if s < e else (lmin >= s) | (lmin < e)
        mk = (dayidx >= t["_ef"]) & (dayidx <= t["_et"]) & (dtarr[pi] == t["day_type"]) & inwin
        rate[pi, mk] = t["rate_per_kwh"]; dcr[pi, mk] = t["demand_charge_per_kw"]; band[pi, mk] = t["tou_band"]; tid[pi, mk] = t["tariff_id"]
    assert (rate > 0).all(), "tariff windows leave gaps"
    tar_df = tar_df.drop(columns=["_ef", "_et"])

    # ---------------- weather ----------------
    temp_q = np.zeros((P, T)); wx_rows = []
    for pi, p in enumerate(pl):
        Th = T // 4; h = np.arange(Th)
        base = [27.0, 18.0][pi % 2] - [6.0, 5.0][pi % 2] * (h / 24 / days)
        diur = [6.0, 5.0][pi % 2] * np.sin(2 * np.pi * ((h % 24) - 9) / 24)
        nz = np.zeros(Th); eps = rng.normal(0, 0.8, Th)
        for i in range(1, Th):
            nz[i] = 0.95 * nz[i - 1] + eps[i]
        temp_h = np.round(base + diur + nz, 1)
        hum = np.round(np.clip(70 - 1.5 * (temp_h - base) - 0.8 * diur + rng.normal(0, 4, Th), 20, 100), 1)
        temp_q[pi] = np.repeat(temp_h, 4)
        ut = gu[pi][::4]
        wx_rows.append(pd.DataFrame(dict(weather_id=[f"WX-{p[0]}-{x:%Y%m%d%H}" for x in ut], plant_id=p[0], observed_at_utc=ut,
                                         temperature_c=temp_h, relative_humidity_pct=hum, source="SYNTHETIC")))
    wx_df = pd.concat(wx_rows, ignore_index=True)

    # ---------------- production batches ----------------
    cands = []
    for mi in range(M):
        pi = machines[mi]["pi"]
        for d in range(days):
            _, wA, wB = cal[(pi, d)]
            if wA: cands.append((mi, d, 0))
            if wB: cands.append((mi, d, 1))
    n = min(a.batches, len(cands))
    sel = np.sort(rng.choice(len(cands), n, replace=False))
    kk = rng.integers(0, 5, n); qq = rng.integers(12, 25, n); ab = rng.random(n) < 0.05; frac = rng.uniform(.3, .8, n)
    lf_b = rng.uniform(.80, .95, n); prod = rng.integers(0, 4, n); y1 = rng.uniform(.97, 1.03, n); y2 = rng.uniform(.96, 1.0, n); y3 = rng.uniform(.9, 1.0, n)
    rows = []
    for j, s in enumerate(sel):
        mi, d, slot = cands[s]; pi = machines[mi]["pi"]
        i0 = d * Q + (24 if slot == 0 else 56) + int(kk[j]); ip = i0 + int(qq[j])
        ie = i0 + max(4, int(qq[j] * frac[j])) if ab[j] else ip
        up = int(round(uph[mi] * qq[j] * 0.25 * y1[j]))
        upr = int(round(up * (ie - i0) / (ip - i0) * y3[j])) if ab[j] else int(round(up * y2[j]))
        rows.append(dict(plant_id=pl[pi][0], machine_id=machines[mi]["id"], shift_id=f"SHF-{pl[pi][0]}-{(start + pd.Timedelta(days=d)):%Y%m%d}-{'AB'[slot]}",
                         product_code=PRODUCTS[prod[j]], start_utc=gu[pi][i0], planned_end_utc=gu[pi][ip], end_utc=gu[pi][ie],
                         units_planned=up, units_produced=upr, status="ABORTED" if ab[j] else "COMPLETED",
                         _mi=mi, _pi=pi, _i0=i0, _i1=ie, _lf=lf_b[j], _d=d))
    bt = pd.DataFrame(rows).sort_values(["start_utc", "machine_id"], kind="stable").reset_index(drop=True)
    bt.insert(0, "batch_id", [f"BATCH-2026-{i + 1:06d}" for i in range(len(bt))])
    run = np.zeros((M, T), bool); lf = np.zeros((M, T)); bid = -np.ones((M, T), int)
    for i, r in bt.iterrows():
        run[r["_mi"], r["_i0"]:r["_i1"]] = True; lf[r["_mi"], r["_i0"]:r["_i1"]] = r["_lf"]; bid[r["_mi"], r["_i0"]:r["_i1"]] = i
    work_m = working[mplant]
    st = np.where(run, 0, np.where(work_m, 1, 2))

    # ---------------- scenarios (documented waste rules) ----------------
    gt = []
    def add_gt(issue, etype, eid, pid, s_ts, e_ts, mag, unit, decision, detail):
        gt.append(dict(issue_type=issue, entity_type=etype, entity_id=eid, plant_id=pid, start_utc=s_ts, end_utc=e_ts,
                       magnitude=mag, magnitude_unit=unit, expected_decision=decision, detail=json.dumps(detail, sort_keys=True)))
    idle_mult = np.ones((M, T)); int_mult = np.ones((M, T)); maint = []
    n_idle = max(1, round(M / 5)); n_int = max(1, round(M / 6))
    idle_m = rng.choice(M, n_idle, replace=False)
    rest = [i for i in range(M) if i not in set(idle_m.tolist()) and not wsens[i]]
    int_m = rng.choice(rest, min(n_int, len(rest)), replace=False)
    def scenario(mi, kind):
        sd = int(days * rng.uniform(.25, .55))
        ln = max(8, int(days * (rng.uniform(.2, .3) if kind == "idle" else rng.uniform(.25, .33))))
        ed = min(sd + ln, days - 2); pi = machines[mi]["pi"]
        s_i, e_i = sd * Q, ed * Q + 22
        if kind == "idle":
            mult = round(float(min(rng.uniform(2.2, 3.0), 0.6 / (idle_kw[mi] / rated[mi]))), 2)
            idle_mult[mi, s_i:e_i] = mult; reason = "STANDBY_CONTROL_FAULT"
        else:
            mult = round(float(rng.uniform(1.15, 1.25)), 3)
            int_mult[mi, s_i:e_i] = mult; reason = "COMPONENT_WEAR"
        maint.append(dict(plant_id=pl[pi][0], machine_id=machines[mi]["id"], event_type="CORRECTIVE", reason_code=reason,
                          scheduled_start_utc=gu[pi][ed * Q + 4], actual_start_utc=gu[pi][ed * Q + 12], actual_end_utc=gu[pi][ed * Q + 22] if ed * Q + 22 < T else gu[pi][-1]))
        add_gt("HIGH_IDLE_CONSUMPTION" if kind == "idle" else "ENERGY_INTENSITY_SHIFT", "Machine", machines[mi]["id"], pl[pi][0],
               gu[pi][s_i], gu[pi][min(e_i, T - 1)], mult, "x idle_kw" if kind == "idle" else "x kWh/unit",
               "RAISE_REDUCE_IDLE_LOAD_RECOMMENDATION" if kind == "idle" else "RAISE_INVESTIGATE_INTENSITY_RECOMMENDATION",
               dict(rule="idle_kw multiplied during working-shift idle intervals; ends at corrective maintenance" if kind == "idle" else
                    "run-state kW multiplied while output per hour unchanged; ends at corrective maintenance", reason_code=reason))
    for mi in idle_m: scenario(int(mi), "idle")
    for mi in int_m: scenario(int(mi), "int")
    # preventive maintenance on Sundays (machines in STANDBY), deterministic
    for mi in range(M):
        pi = machines[mi]["pi"]
        sundays = [d for d in range(days) if (start + pd.Timedelta(days=d)).weekday() == 6]
        if not sundays: continue
        d = int(rng.choice(sundays))
        maint.append(dict(plant_id=pl[pi][0], machine_id=machines[mi]["id"], event_type="PREVENTIVE", reason_code="SCHEDULED_SERVICE",
                          scheduled_start_utc=gu[pi][max(0, d * Q - 28)], actual_start_utc=gu[pi][d * Q + 32], actual_end_utc=gu[pi][d * Q + 48]))
    # peak spikes: simultaneous restart of several machines inside the PEAK band
    spike_bump = np.zeros((M, T)); spikes = []
    protected = np.zeros((Mt, T), bool)
    for k in range(max(3, round(days / 7))):
        pi = k % P
        while True:
            d = int(rng.integers(3, days - 1))
            if cal[(pi, d)][2]: break
        i = d * Q + int(rng.integers(56, 78))
        ms = [x for x in range(M) if machines[x]["pi"] == pi]
        pick = rng.choice(ms, min(4, len(ms)), replace=False)
        for x in pick:
            spike_bump[x, i] += rated[x] * 0.9; protected[machines[x]["meter"], i - 1:i + 2] = True
        protected[main_of[pi], i - 1:i + 2] = True
        spikes.append((pi, i, [machines[int(x)]["id"] for x in pick], float(sum(rated[int(x)] * .9 for x in pick))))

    # ---------------- power model ----------------
    wf = np.ones((M, T))
    for mi in range(M):
        if wsens[mi]: wf[mi] = 1 + 0.006 * np.maximum(0, temp_q[machines[mi]["pi"]] - 22)
    noise = 1 + rng.normal(0, 0.02, (M, T))
    kw = np.where(run, rated[:, None] * lf * int_mult, np.where(work_m, idle_kw[:, None] * idle_mult, stby[:, None])) * wf * noise + spike_bump
    pk = 1 + rng.uniform(.03, .15, (M, T)); pks = rng.uniform(1.5, 2.0, (M, T))
    prev = np.concatenate([-np.ones((M, 1), int), bid[:, :-1]], axis=1)
    pk = np.where((bid >= 0) & (bid != prev), pks, pk)
    pk = np.where(spike_bump > 0, 1.15, pk)
    meter_kw = np.zeros((Mt, T)); meter_pk = np.zeros((Mt, T))
    for pi in range(P):
        idx = [i for i in range(M) if machines[i]["pi"] == pi]
        sub = kw[idx].sum(0); extra = (kw * (pk - 1))[idx].sum(0)
        occ = np.where(working[pi], 1.0, 0.45)
        base = (10 + 0.05 * rated[idx].sum()) * occ * (1 + 0.02 * np.maximum(0, temp_q[pi] - 18)) * (1 + rng.normal(0, .03, T))
        mm = main_of[pi]; meter_kw[mm] = sub + base; meter_pk[mm] = sub + base + 0.4 * extra + base * rng.uniform(0, .05, T)
    for mi in range(M):
        mm = machines[mi]["meter"]; meter_kw[mm] = kw[mi]; meter_pk[mm] = kw[mi] * pk[mi]
    e_r = np.round(meter_kw / 4, 3); kw_r = np.round(e_r * 4, 3); pk_r = np.round(np.maximum(meter_pk, kw_r), 3)
    reg = np.round(reg0[:, None] + np.cumsum(e_r, axis=1), 3)

    # ---------------- gaps + injected reading anomalies ----------------
    miss = np.zeros((Mt, T), bool)
    for mt in range(Mt):
        pi = meters[mt]["pi"]
        for _ in range(int(rng.integers(1, 4))):
            ln = int(rng.integers(2, 33))
            for _try in range(30):
                s0 = int(rng.integers(8, T - 40))
                if not protected[mt, s0 - 2:s0 + ln + 2].any() and not miss[mt, s0 - 3:s0 + ln + 3].any():
                    miss[mt, s0:s0 + ln] = True
                    add_gt("METER_GAP", "Meter", meters[mt]["id"], pl[pi][0], gu[pi][s0], gu[pi][s0 + ln - 1] + pd.Timedelta(minutes=15), ln, "intervals",
                           "TREAT_AS_MISSING_DO_NOT_IMPUTE_SILENTLY",
                           dict(rule="communication outage; rows absent, register keeps counting", lost_kwh=round(float(e_r[mt, s0:s0 + ln].sum()), 3)))
                    break
    for (pi, i, mnames, extra_kw) in spikes:
        add_gt("PEAK_DEMAND_SPIKE", "Meter", meters[main_of[pi]]["id"], pl[pi][0], gu[pi][i], gu[pi][i] + pd.Timedelta(minutes=15),
               round(extra_kw, 1), "kW added", "RAISE_STAGGER_PEAK_STARTUPS_RECOMMENDATION",
               dict(rule="simultaneous restart inside PEAK band", machines=mnames))
    ok = ~miss; ok[:, 1:] &= ~miss[:, :-1]; ok[:, :-1] &= ~miss[:, 1:]; ok[:, :2] = False
    scale = (a.meters * a.days) / 1800.0
    def cnt_(b, lo=2): return max(lo, int(round(b * scale)))
    used = np.zeros((Mt, T), bool)
    def take(n, extra_mask=None, subs_only=False):
        m = ok & ~used
        if extra_mask is not None: m = m & extra_mask
        if subs_only: m = m & np.array([x["type"] == "SUB" for x in meters])[:, None]
        pool = np.flatnonzero(m.ravel()); n = min(n, len(pool))
        pick = np.sort(rng.choice(pool, n, replace=False)); used.ravel()[pick] = True
        return [(int(p) // T, int(p) % T) for p in pick]
    e_out = e_r.copy(); machine_arr = np.empty((Mt, T), dtype=object)
    for mt in meters:
        if mt["type"] == "SUB": machine_arr[meters.index(mt), :] = machines[mt["machine"]]["id"]
    rid = lambda mt, t: "ENG-%s-%s" % (meters[mt]["id"], tsc[meters[mt]["pi"]][t])
    for (mt, t) in take(cnt_(25), kw_r > 5):
        e_out[mt, t] = kw_r[mt, t]; pi = meters[mt]["pi"]
        add_gt("KW_KWH_CONFUSION", "EnergyReading", rid(mt, t), pl[pi][0], gu[pi][t], gu[pi][t] + pd.Timedelta(minutes=15), 4.0, "x overstated",
               "REPAIR_ENERGY_FROM_DEMAND_KW_DIV_4", dict(rule="demand kW stored in energy_kwh field", correct_energy_kwh=float(e_r[mt, t])))
    for (mt, t) in take(cnt_(25), None, True):
        pi = meters[mt]["pi"]; wrong = [x["id"] for x in machines if x["id"] != machines[meters[mt]["machine"]]["id"]]
        machine_arr[mt, t] = wrong[int(rng.integers(0, len(wrong)))]
        add_gt("MACHINE_OUTSIDE_METER_HIERARCHY", "EnergyReading", rid(mt, t), pl[pi][0], gu[pi][t], gu[pi][t] + pd.Timedelta(minutes=15), 1, "reading",
               "REJECT_MACHINE_ATTRIBUTION_USE_ASSIGNED_MACHINE", dict(rule="machine_id not assigned to this meter in MachineMeterAssignment", correct_machine_id=machines[meters[mt]["machine"]]["id"]))
    for (mt, t) in take(cnt_(3, 1)):
        pi = meters[mt]["pi"]; J = round(float(rng.uniform(.04, .09) * e_r[mt].sum() / days), 3); reg[mt, t:] = np.round(reg[mt, t:] + J, 3)
        add_gt("METER_TOTAL_MISMATCH", "EnergyReading", rid(mt, t), pl[pi][0], gu[pi][t], gu[pi][t] + pd.Timedelta(minutes=15), J, "kWh register jump",
               "FLAG_REGISTER_VS_INTERVAL_DISAGREEMENT", dict(rule="register steps up by more than the interval energy; interval energy itself is correct"))
    dups = take(cnt_(30))
    frames = []
    for mt in range(Mt):
        pi = meters[mt]["pi"]; pr = ~miss[mt]; ts = gu[pi][pr]
        frames.append(pd.DataFrame(dict(reading_id=["ENG-%s-%s" % (meters[mt]["id"], s) for s in tsc[pi][pr]], meter_id=meters[mt]["id"],
                                        interval_start_utc=ts, interval_end_utc=ts + pd.Timedelta(minutes=15), energy_kwh=e_out[mt][pr],
                                        demand_kw_avg=kw_r[mt][pr], demand_kw_peak=pk_r[mt][pr], register_kwh=reg[mt][pr],
                                        machine_id=machine_arr[mt][pr], ingest_seq=1)))
    rd = pd.concat(frames, ignore_index=True)
    dup_ids = [rid(mt, t) for mt, t in dups]
    dup = rd[rd["reading_id"].isin(dup_ids)].copy()
    dup["reading_id"] = dup["reading_id"] + "-R2"; dup["ingest_seq"] = 2
    for (mt, t), oid in zip(dups, dup_ids):
        pi = meters[mt]["pi"]
        add_gt("DUPLICATE_READING", "EnergyReading", oid + "-R2", pl[pi][0], gu[pi][t], gu[pi][t] + pd.Timedelta(minutes=15), 1, "extra row",
               "DEDUPLICATE_KEEP_INGEST_SEQ_1", dict(original_reading_id=oid))
    rd = pd.concat([rd, dup], ignore_index=True).sort_values(["meter_id", "interval_start_utc", "ingest_seq"], kind="stable").reset_index(drop=True)
    # tariff timezone mismatch ground truth
    bad = tar_df[tar_df["timezone"] != tar_df["plant_id"].map({p[0]: p[2] for p in pl})]
    for _, r in bad.iterrows():
        add_gt("TARIFF_TIMEZONE_MISMATCH", "Tariff", r["tariff_id"], r["plant_id"], None, None, 1, "tariff row",
               "INTERPRET_WINDOWS_IN_PLANT_TIMEZONE", dict(declared_timezone=r["timezone"], plant_timezone=[p[2] for p in pl if p[0] == r["plant_id"]][0]))

    # ---------------- derived tables ----------------
    pid_of_m = np.array([m["pi"] for m in meters])
    rows = []
    for mt in range(Mt):
        pi = pid_of_m[mt]; pr = ~miss[mt]
        rows.append(pd.DataFrame(dict(reading_id=["ENG-%s-%s" % (meters[mt]["id"], s) for s in tsc[pi][pr]], tariff_id=tid[pi][pr], tou_band=band[pi][pr],
                                      rate_per_kwh=rate[pi][pr], energy_kwh_clean=e_r[mt][pr], cost=np.round(e_r[mt][pr] * rate[pi][pr], 4))))
    cost_df = pd.concat(rows, ignore_index=True)
    # daily summary
    dsum = []
    units_by = bt.groupby(["_pi", "_d"])["units_produced"].sum().to_dict()
    for pi, p in enumerate(pl):
        mm = main_of[pi]; subs = [m for m in range(Mt) if meters[m]["pi"] == pi and meters[m]["type"] == "SUB"]
        for d in range(days):
            sl = slice(d * Q, (d + 1) * Q)
            mk = ~miss[mm, sl]; mkw = float(e_r[mm, sl][mk].sum())
            skw = float(sum(e_r[s, sl][~miss[s, sl]].sum() for s in subs))
            gaps = int(sum(miss[x, sl].sum() for x in [mm] + subs)); units = int(units_by.get((pi, d), 0)); okd = gaps == 0
            dsum.append(dict(summary_id=f"DSUM-{p[0]}-{(start + pd.Timedelta(days=d)):%Y%m%d}", plant_id=p[0], summary_date=(start + pd.Timedelta(days=d)).strftime("%Y-%m-%d"),
                             main_kwh=round(mkw, 3), submeter_kwh=round(skw, 3), unmetered_kwh=round(mkw - skw, 3) if okd else None, units_produced=units,
                             energy_intensity_kwh_per_unit=round(mkw / units, 4) if okd and units > 0 else None,
                             energy_cost=round(float((e_r[mm, sl] * rate[pi, sl])[mk].sum()), 4), peak_kw=float(kw_r[mm, sl][mk].max()) if mk.any() else 0.0,
                             missing_intervals=gaps, reconcile_status="OK" if okd else "GAP_AFFECTED"))
    dsum_df = pd.DataFrame(dsum)
    # batch energy
    be = []
    for i, r in bt.iterrows():
        mi, pi, sl = r["_mi"], r["_pi"], slice(r["_i0"], r["_i1"]); mt = machines[mi]["meter"]; pr = ~miss[mt, sl]
        e = float(e_r[mt, sl][pr].sum()); covr = float(pr.mean())
        inten = e / r["units_produced"] if covr == 1 and r["units_produced"] > 0 else None
        be.append(dict(batch_id=r["batch_id"], machine_id=r["machine_id"], meter_id=meters[mt]["id"], energy_kwh=round(e, 3), coverage_ratio=round(covr, 4),
                       energy_cost=round(float((e_r[mt, sl] * rate[pi, sl])[pr].sum()), 4), intensity_kwh_per_unit=round(inten, 5) if inten else None,
                       _status=r["status"], _d=r["_d"], _mi=mi))
    be_df = pd.DataFrame(be)
    bdays = int(days * .23); base_i = {}
    for mi in range(M):
        z = be_df[(be_df._mi == mi) & (be_df._status == "COMPLETED") & be_df.intensity_kwh_per_unit.notna() & (be_df._d < bdays)]
        base_i[mi] = float(z.intensity_kwh_per_unit.median()) if len(z) >= 4 else None
    be_df["baseline_intensity"] = [round(base_i[m], 5) if base_i[m] else None for m in be_df._mi]
    be_df["intensity_ratio"] = [round(i / b, 4) if (i and b) else None for i, b in zip(be_df.intensity_kwh_per_unit, be_df.baseline_intensity)]
    # monthly demand
    md = []
    for pi, p in enumerate(pl):
        mm = main_of[pi]; months = gl.strftime("%Y-%m").to_numpy()
        for mon in sorted(set(months)):
            mk = (months == mon) & (band[pi] == "PEAK") & ~miss[mm]
            if not mk.any(): continue
            vals = kw_r[mm][mk]; ix = np.flatnonzero(mk)[int(np.argmax(vals))]
            md.append(dict(demand_id=f"MDEM-{p[0]}-{mon.replace('-', '')}", plant_id=p[0], month=mon, peak_kw=float(vals.max()), peak_ts_utc=gu[pi][ix],
                           p95_peak_band_kw=round(float(np.percentile(vals, 95)), 3), demand_charge_per_kw=float(dcr[pi, ix]),
                           demand_charge=round(float(vals.max() * dcr[pi, ix]), 2), _n=len(set(dayidx[mk])), _ix=ix, _pi=pi))
    md_df = pd.DataFrame(md)

    # ---------------- state periods ----------------
    sp = []
    for mi in range(M):
        pi = machines[mi]["pi"]; code = st[mi] * 10_000_000 + np.where(run[mi], bid[mi] + 1, 0)
        cuts = np.concatenate([[0], np.flatnonzero(np.diff(code)) + 1, [T]])
        for k in range(len(cuts) - 1):
            s0, e0 = cuts[k], cuts[k + 1]; s_ = int(st[mi, s0])
            sp.append(dict(period_id=f"SPD-{machines[mi]['id']}-{k + 1:05d}", machine_id=machines[mi]["id"], state=["RUN", "IDLE", "STANDBY"][s_], start_utc=gu[pi][s0],
                           end_utc=gu[pi][e0] if e0 < T else gu[pi][-1] + pd.Timedelta(minutes=15), batch_id=bt.loc[bid[mi, s0], "batch_id"] if s_ == 0 else None))
    sp_df = pd.DataFrame(sp)

    # ---------------- maintenance + recommendations (detector rules on measured data) ----------------
    mn = pd.DataFrame(maint).sort_values(["actual_start_utc", "machine_id"], kind="stable").reset_index(drop=True)
    mn.insert(0, "maintenance_id", [f"MNT-2026-{i + 1:06d}" for i in range(len(mn))]); mn["status"] = "COMPLETED"
    kw_meas = np.where(miss[[machines[m]["meter"] for m in range(M)]], np.nan, kw_r[[machines[m]["meter"] for m in range(M)]])
    recs = []; consec = 5 if days >= 60 else 3; bd = max(5, int(days * .15))
    def mkrec(pi, meter, mach, typ, rule, created, es, ee, b, o, unit, kwh, kwn, cost, status=None):
        recs.append(dict(plant_id=pl[pi][0], meter_id=meter, machine_id=mach, rec_type=typ, rule_id=rule, created_at_utc=created, evidence_start_utc=es, evidence_end_utc=ee,
                         baseline_value=round(b, 4), observed_value=round(o, 4), value_unit=unit, expected_savings_kwh=None if kwh is None else round(kwh, 2),
                         expected_savings_kw=None if kwn is None else round(kwn, 2), expected_savings_cost=round(cost, 2), currency=pl[pi][5], savings_horizon_days=30))
    for mi in range(M):
        pi = machines[mi]["pi"]; daily = np.full(days, np.nan); cn = np.zeros(days)
        for d in range(days):
            sl = slice(d * Q, (d + 1) * Q); m_ = (st[mi, sl] == 1) & ~np.isnan(kw_meas[mi, sl])
            if m_.sum() >= 4: daily[d] = kw_meas[mi, sl][m_].mean(); cn[d] = m_.sum()
        if np.isfinite(daily[:bd]).sum() < 3: continue
        base = np.nanmedian(daily[:bd]); flag = np.nan_to_num(daily, nan=0) > 1.5 * base
        for j in range(consec - 1, days):
            if flag[j - consec + 1:j + 1].all():
                obs = float(np.nanmean(daily[j - consec + 1:j + 1])); idle_h = float(np.nanmean(cn[np.isfinite(daily)]) * .25)
                avg_rate = float(rate[pi][st[mi] == 1].mean()); kwh = (obs - base) * idle_h * 30
                ce = min((j + 1) * Q, T - 1)
                mkrec(pi, meters[machines[mi]["meter"]]["id"], machines[mi]["id"], "REDUCE_IDLE_LOAD", "R-IDLE-1", gu[pi][ce], gu[pi][(j - consec + 1) * Q], gu[pi][ce], base, obs, "kW", kwh, None, kwh * avg_rate)
                break
    for mi in range(M):
        pi = machines[mi]["pi"]; z = be_df[(be_df._mi == mi) & (be_df._status == "COMPLETED") & be_df.intensity_ratio.notna()].copy()
        z = bt.loc[bt.batch_id.isin(z.batch_id)].merge(z[["batch_id", "intensity_ratio", "baseline_intensity"]], on="batch_id")
        if len(z) < 12 or base_i[mi] is None: continue
        rm = z.intensity_ratio.rolling(8).median()
        hit = rm[(rm >= 1.10) & (z._d >= bdays)]
        if len(hit):
            j = hit.index[0]; obs_int = float(rm[j] * base_i[mi]); upd = float(bt[bt.machine_id == machines[mi]["id"]].units_produced.sum() / days)
            kwh = (obs_int - base_i[mi]) * upd * 30; avg_rate = float(rate[pi][st[mi] == 0].mean())
            mkrec(pi, meters[machines[mi]["meter"]]["id"], machines[mi]["id"], "INVESTIGATE_INTENSITY_SHIFT", "R-INT-1", z.loc[j, "end_utc"], z.loc[j - 7, "start_utc"], z.loc[j, "end_utc"], base_i[mi], obs_int, "kWh/unit", kwh, None, kwh * avg_rate)
    for _, r in md_df.iterrows():
        if r["_n"] >= max(10, days // 6) and r["peak_kw"] > 1.2 * r["p95_peak_band_kw"]:
            pi = r["_pi"]; dk = r["peak_kw"] - r["p95_peak_band_kw"]
            ix = r["_ix"]; mkrec(pi, meters[main_of[pi]]["id"], None, "STAGGER_PEAK_STARTUPS", "R-PEAK-1", gu[pi][ix] + pd.Timedelta(minutes=15), gu[pi][ix], gu[pi][ix] + pd.Timedelta(minutes=15),
                                 r["p95_peak_band_kw"], r["peak_kw"], "kW", None, dk, dk * r["demand_charge_per_kw"])
    rec = pd.DataFrame(recs)
    hist = []
    end_ts = gu[0][-1] + pd.Timedelta(minutes=15)
    if len(rec):
        rec = rec.sort_values(["created_at_utc", "rec_type", "meter_id"], kind="stable").reset_index(drop=True)
        rec.insert(0, "recommendation_id", [f"REC-2026-{i + 1:06d}" for i in range(len(rec))])
        sts = []
        for _, r in rec.iterrows():
            ack = r["created_at_utc"] + pd.Timedelta(hours=26); implemented = None
            if r["machine_id"]:
                m2 = mn[(mn.machine_id == r["machine_id"]) & (mn.event_type == "CORRECTIVE") & (mn.actual_start_utc > r["created_at_utc"]) & (mn.actual_start_utc < r["created_at_utc"] + pd.Timedelta(days=45))]
                if len(m2): implemented = m2.iloc[0]["actual_end_utc"]
                if implemented is not None: s_ = "IMPLEMENTED"
                else: s_ = "ACKNOWLEDGED" if ack < end_ts else "OPEN"
            else:
                s_ = "ACKNOWLEDGED" if ack < end_ts else "OPEN"
            sts.append(s_); hist.append((r["recommendation_id"], "Recommendation", None, "OPEN", r["created_at_utc"], 0))
            if s_ in ("ACKNOWLEDGED", "IMPLEMENTED"): hist.append((r["recommendation_id"], "Recommendation", "OPEN", "ACKNOWLEDGED", ack, 1))
            if s_ == "IMPLEMENTED": hist.append((r["recommendation_id"], "Recommendation", "ACKNOWLEDGED", "IMPLEMENTED", max(implemented, ack + pd.Timedelta(minutes=1)), 2))
        rec["status"] = sts
    else:
        rec = pd.DataFrame(columns=cols("Recommendation"))
    for _, r in bt.iterrows():
        hist += [(r["batch_id"], "ProductionBatch", None, "PLANNED", r["start_utc"] - pd.Timedelta(hours=12), 0), (r["batch_id"], "ProductionBatch", "PLANNED", "RUNNING", r["start_utc"], 1),
                 (r["batch_id"], "ProductionBatch", "RUNNING", r["status"], r["end_utc"], 2)]
    for _, r in mn.iterrows():
        hist += [(r["maintenance_id"], "MaintenanceEvent", None, "SCHEDULED", r["scheduled_start_utc"] - pd.Timedelta(hours=1), 0), (r["maintenance_id"], "MaintenanceEvent", "SCHEDULED", "IN_PROGRESS", r["actual_start_utc"], 1),
                 (r["maintenance_id"], "MaintenanceEvent", "IN_PROGRESS", "COMPLETED", r["actual_end_utc"], 2)]
    hdf = pd.DataFrame(hist, columns=["entity_id", "entity_type", "from_state", "to_state", "changed_at_utc", "_o"]).sort_values(["changed_at_utc", "entity_id", "_o"], kind="stable").reset_index(drop=True)
    hdf.insert(0, "history_id", [f"HST-2026-{i + 1:06d}" for i in range(len(hdf))]); hdf = hdf.drop(columns=["_o"])

    gt_df = pd.DataFrame(gt)
    gt_df = gt_df.sort_values(["issue_type", "entity_id", "start_utc"], kind="stable", na_position="last").reset_index(drop=True)
    gt_df.insert(0, "gt_id", [f"GT-{i + 1:06d}" for i in range(len(gt_df))])
    tables = {"Plant": plant, "Meter": meter_df, "Machine": machine_df, "MachineMeterAssignment": assign_df, "Shift": shift_df, "TariffCalendar": cal_df,
              "Tariff": tar_df, "WeatherObservation": wx_df, "ProductionBatch": bt, "EnergyReading": rd, "MaintenanceEvent": mn, "Recommendation": rec,
              "StatusHistory": hdf, "MachineStatePeriod": sp_df, "ReadingCost": cost_df, "DailyPlantSummary": dsum_df, "BatchEnergy": be_df, "MonthlyDemand": md_df}
    tables = {k: v[cols(k)] for k, v in tables.items()}
    return tables, gt_df[GT_COLS]


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()


def export(a, tables, gt_df):
    out = a.out
    for sub in ("data", "json", "ground_truth", "sql", "docs"): os.makedirs(f"{out}/{sub}", exist_ok=True)
    ft = {k: fmt_df(v) for k, v in tables.items()}
    for k, v in ft.items():
        v.to_csv(f"{out}/data/{FILES[k]}.csv", index=False, lineterminator="\n")
        if k not in LARGE: v.to_json(f"{out}/json/{FILES[k]}.json", orient="records", indent=1)
    g = fmt_df(gt_df); g.to_csv(f"{out}/ground_truth/ground_truth.csv", index=False, lineterminator="\n"); g.to_json(f"{out}/ground_truth/ground_truth.json", orient="records", indent=1)
    open(f"{out}/sql/schema.sql", "w").write(ddl())
    open(f"{out}/docs/data_dictionary.md", "w").write(dd_markdown())
    pd.DataFrame([r for rows in DD.values() for r in rows]).to_csv(f"{out}/docs/data_dictionary.csv", index=False, lineterminator="\n")
    if not a.no_sql:
        con = sqlite3.connect(":memory:"); con.executescript(ddl())
        for k in DD:
            d = ft[k].astype(object).where(ft[k].notna(), None)
            con.executemany(f"INSERT INTO {FILES[k]} ({','.join(d.columns)}) VALUES ({','.join('?' * len(d.columns))})", d.itertuples(index=False, name=None))
        con.commit(); con.execute("PRAGMA foreign_keys=ON")
        assert con.execute("PRAGMA foreign_key_check").fetchall() == [], "SQLite FK check failed"
        with gzip.GzipFile(f"{out}/sql/seed.sql.gz", "wb", mtime=0) as z:
            for line in con.iterdump(): z.write((line + "\n").encode())
        con.close()
    files = {}
    for root, _, fs in sorted(os.walk(out)):
        for f in sorted(fs):
            if f in ("manifest.json", "validation_summary.json", "validation_summary.md"): continue
            p = os.path.join(root, f); rel = os.path.relpath(p, out)
            files[rel] = dict(sha256=sha(p), bytes=os.path.getsize(p), rows=(len(ft[[k for k in FILES if FILES[k] == f[:-4]][0]]) if rel.startswith("data/") else None))
    cmd = f"python generate.py --seed {a.seed} --start {a.start} --days {a.days} --plants {a.plants} --meters {a.meters} --batches {a.batches}" + (" --no-sql" if a.no_sql else "")
    json.dump(dict(generator="generate.py", command=cmd, seed=a.seed, parameters=dict(start=a.start, days=a.days, plants=a.plants, meters=a.meters, batches=a.batches),
                   external_data=[], provenance="Fully synthetic. No external datasets, scraped data, or personal information were used. Plant names are fictional.",
                   files=files), open(f"{out}/manifest.json", "w"), indent=1, sort_keys=True)
    print("wrote", out, "|", {FILES[k]: len(v) for k, v in tables.items()}, "| ground truth rows:", len(gt_df))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20261022); ap.add_argument("--start", default="2026-07-01")
    ap.add_argument("--days", type=int, default=90); ap.add_argument("--plants", type=int, default=2)
    ap.add_argument("--meters", type=int, default=20); ap.add_argument("--batches", type=int, default=2000)
    ap.add_argument("--out", default="out"); ap.add_argument("--no-sql", action="store_true")
    ap.add_argument("--scale", choices=["full", "starter"], default="full", help="starter = 6 meters, 30 days, 200 batches")
    a = ap.parse_args()
    if a.scale == "starter": a.meters, a.days, a.batches = 6, 30, 200
    tables, gt_df = build(a); export(a, tables, gt_df)
