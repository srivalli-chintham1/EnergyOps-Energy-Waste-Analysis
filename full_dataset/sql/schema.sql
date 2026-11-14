-- Generated from the data dictionary. SQLite dialect.
PRAGMA foreign_keys = ON;
CREATE TABLE plant (
  plant_id TEXT NOT NULL,
  plant_name TEXT NOT NULL,
  timezone TEXT NOT NULL,
  latitude REAL NOT NULL,
  longitude REAL NOT NULL,
  currency TEXT NOT NULL,
  status TEXT NOT NULL,
  commissioned_date TEXT NOT NULL,
  PRIMARY KEY (plant_id)
);
CREATE TABLE meter (
  meter_id TEXT NOT NULL,
  plant_id TEXT NOT NULL,
  meter_type TEXT NOT NULL,
  parent_meter_id TEXT,
  energy_unit TEXT NOT NULL,
  demand_unit TEXT NOT NULL,
  sampling_minutes INTEGER NOT NULL,
  install_date TEXT NOT NULL,
  register_start_kwh REAL NOT NULL,
  status TEXT NOT NULL,
  PRIMARY KEY (meter_id),
  FOREIGN KEY (plant_id) REFERENCES plant(plant_id),
  FOREIGN KEY (parent_meter_id) REFERENCES meter(meter_id)
);
CREATE TABLE machine (
  machine_id TEXT NOT NULL,
  plant_id TEXT NOT NULL,
  machine_type TEXT NOT NULL,
  rated_kw REAL NOT NULL,
  idle_kw REAL NOT NULL,
  standby_kw REAL NOT NULL,
  units_per_hour REAL NOT NULL,
  weather_sensitive INTEGER NOT NULL,
  commissioned_date TEXT NOT NULL,
  status TEXT NOT NULL,
  PRIMARY KEY (machine_id),
  FOREIGN KEY (plant_id) REFERENCES plant(plant_id)
);
CREATE TABLE machine_meter_assignment (
  assignment_id TEXT NOT NULL,
  machine_id TEXT NOT NULL,
  meter_id TEXT NOT NULL,
  relation TEXT NOT NULL,
  effective_from TEXT NOT NULL,
  effective_to TEXT,
  PRIMARY KEY (assignment_id),
  FOREIGN KEY (machine_id) REFERENCES machine(machine_id),
  FOREIGN KEY (meter_id) REFERENCES meter(meter_id)
);
CREATE TABLE shift (
  shift_id TEXT NOT NULL,
  plant_id TEXT NOT NULL,
  shift_date TEXT NOT NULL,
  shift_code TEXT NOT NULL,
  start_utc TEXT NOT NULL,
  end_utc TEXT NOT NULL,
  is_working INTEGER NOT NULL,
  PRIMARY KEY (shift_id),
  FOREIGN KEY (plant_id) REFERENCES plant(plant_id)
);
CREATE TABLE tariff_calendar (
  calendar_id TEXT NOT NULL,
  plant_id TEXT NOT NULL,
  calendar_date TEXT NOT NULL,
  day_type TEXT NOT NULL,
  holiday_name TEXT,
  PRIMARY KEY (calendar_id),
  FOREIGN KEY (plant_id) REFERENCES plant(plant_id)
);
CREATE TABLE tariff (
  tariff_id TEXT NOT NULL,
  plant_id TEXT NOT NULL,
  day_type TEXT NOT NULL,
  tou_band TEXT NOT NULL,
  window_start_local TEXT NOT NULL,
  window_end_local TEXT NOT NULL,
  timezone TEXT NOT NULL,
  rate_per_kwh REAL NOT NULL,
  demand_charge_per_kw REAL NOT NULL,
  currency TEXT NOT NULL,
  effective_from TEXT NOT NULL,
  effective_to TEXT,
  PRIMARY KEY (tariff_id),
  FOREIGN KEY (plant_id) REFERENCES plant(plant_id)
);
CREATE TABLE weather_observation (
  weather_id TEXT NOT NULL,
  plant_id TEXT NOT NULL,
  observed_at_utc TEXT NOT NULL,
  temperature_c REAL NOT NULL,
  relative_humidity_pct REAL NOT NULL,
  source TEXT NOT NULL,
  PRIMARY KEY (weather_id),
  FOREIGN KEY (plant_id) REFERENCES plant(plant_id)
);
CREATE TABLE production_batch (
  batch_id TEXT NOT NULL,
  plant_id TEXT NOT NULL,
  machine_id TEXT NOT NULL,
  shift_id TEXT NOT NULL,
  product_code TEXT NOT NULL,
  start_utc TEXT NOT NULL,
  planned_end_utc TEXT NOT NULL,
  end_utc TEXT NOT NULL,
  units_planned INTEGER NOT NULL,
  units_produced INTEGER NOT NULL,
  status TEXT NOT NULL,
  PRIMARY KEY (batch_id),
  FOREIGN KEY (plant_id) REFERENCES plant(plant_id),
  FOREIGN KEY (machine_id) REFERENCES machine(machine_id),
  FOREIGN KEY (shift_id) REFERENCES shift(shift_id)
);
CREATE TABLE energy_reading (
  reading_id TEXT NOT NULL,
  meter_id TEXT NOT NULL,
  interval_start_utc TEXT NOT NULL,
  interval_end_utc TEXT NOT NULL,
  energy_kwh REAL NOT NULL,
  demand_kw_avg REAL NOT NULL,
  demand_kw_peak REAL NOT NULL,
  register_kwh REAL NOT NULL,
  machine_id TEXT,
  ingest_seq INTEGER NOT NULL,
  PRIMARY KEY (reading_id),
  FOREIGN KEY (meter_id) REFERENCES meter(meter_id),
  FOREIGN KEY (machine_id) REFERENCES machine(machine_id)
);
CREATE TABLE maintenance_event (
  maintenance_id TEXT NOT NULL,
  plant_id TEXT NOT NULL,
  machine_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  reason_code TEXT NOT NULL,
  scheduled_start_utc TEXT NOT NULL,
  actual_start_utc TEXT NOT NULL,
  actual_end_utc TEXT NOT NULL,
  status TEXT NOT NULL,
  PRIMARY KEY (maintenance_id),
  FOREIGN KEY (plant_id) REFERENCES plant(plant_id),
  FOREIGN KEY (machine_id) REFERENCES machine(machine_id)
);
CREATE TABLE recommendation (
  recommendation_id TEXT NOT NULL,
  plant_id TEXT NOT NULL,
  meter_id TEXT NOT NULL,
  machine_id TEXT,
  rec_type TEXT NOT NULL,
  rule_id TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  evidence_start_utc TEXT NOT NULL,
  evidence_end_utc TEXT NOT NULL,
  baseline_value REAL NOT NULL,
  observed_value REAL NOT NULL,
  value_unit TEXT NOT NULL,
  expected_savings_kwh REAL,
  expected_savings_kw REAL,
  expected_savings_cost REAL NOT NULL,
  currency TEXT NOT NULL,
  savings_horizon_days INTEGER NOT NULL,
  status TEXT NOT NULL,
  PRIMARY KEY (recommendation_id),
  FOREIGN KEY (plant_id) REFERENCES plant(plant_id),
  FOREIGN KEY (meter_id) REFERENCES meter(meter_id),
  FOREIGN KEY (machine_id) REFERENCES machine(machine_id)
);
CREATE TABLE status_history (
  history_id TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  from_state TEXT,
  to_state TEXT NOT NULL,
  changed_at_utc TEXT NOT NULL,
  PRIMARY KEY (history_id)
);
CREATE TABLE machine_state_period (
  period_id TEXT NOT NULL,
  machine_id TEXT NOT NULL,
  state TEXT NOT NULL,
  start_utc TEXT NOT NULL,
  end_utc TEXT NOT NULL,
  batch_id TEXT,
  PRIMARY KEY (period_id),
  FOREIGN KEY (machine_id) REFERENCES machine(machine_id),
  FOREIGN KEY (batch_id) REFERENCES production_batch(batch_id)
);
CREATE TABLE reading_cost (
  reading_id TEXT NOT NULL,
  tariff_id TEXT NOT NULL,
  tou_band TEXT NOT NULL,
  rate_per_kwh REAL NOT NULL,
  energy_kwh_clean REAL NOT NULL,
  cost REAL NOT NULL,
  PRIMARY KEY (reading_id),
  FOREIGN KEY (reading_id) REFERENCES energy_reading(reading_id),
  FOREIGN KEY (tariff_id) REFERENCES tariff(tariff_id)
);
CREATE TABLE daily_plant_summary (
  summary_id TEXT NOT NULL,
  plant_id TEXT NOT NULL,
  summary_date TEXT NOT NULL,
  main_kwh REAL NOT NULL,
  submeter_kwh REAL NOT NULL,
  unmetered_kwh REAL,
  units_produced INTEGER NOT NULL,
  energy_intensity_kwh_per_unit REAL,
  energy_cost REAL NOT NULL,
  peak_kw REAL NOT NULL,
  missing_intervals INTEGER NOT NULL,
  reconcile_status TEXT NOT NULL,
  PRIMARY KEY (summary_id),
  FOREIGN KEY (plant_id) REFERENCES plant(plant_id)
);
CREATE TABLE batch_energy (
  batch_id TEXT NOT NULL,
  machine_id TEXT NOT NULL,
  meter_id TEXT NOT NULL,
  energy_kwh REAL NOT NULL,
  coverage_ratio REAL NOT NULL,
  energy_cost REAL NOT NULL,
  intensity_kwh_per_unit REAL,
  baseline_intensity REAL,
  intensity_ratio REAL,
  PRIMARY KEY (batch_id),
  FOREIGN KEY (batch_id) REFERENCES production_batch(batch_id),
  FOREIGN KEY (machine_id) REFERENCES machine(machine_id),
  FOREIGN KEY (meter_id) REFERENCES meter(meter_id)
);
CREATE TABLE monthly_demand (
  demand_id TEXT NOT NULL,
  plant_id TEXT NOT NULL,
  month TEXT NOT NULL,
  peak_kw REAL NOT NULL,
  peak_ts_utc TEXT NOT NULL,
  p95_peak_band_kw REAL NOT NULL,
  demand_charge_per_kw REAL NOT NULL,
  demand_charge REAL NOT NULL,
  PRIMARY KEY (demand_id),
  FOREIGN KEY (plant_id) REFERENCES plant(plant_id)
);
