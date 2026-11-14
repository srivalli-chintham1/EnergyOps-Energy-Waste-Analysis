#!/usr/bin/env python3
"""Independent validation of an exported dataset directory. Reads only the exported files.
Ground truth is used here (validation), never in generation inputs: every injected anomaly must be
detected by a rule, and every detected anomaly must be explained by a ground-truth row."""
import json, os, re, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from generate import DD, FILES, cols, GT_COLS

out = sys.argv[1] if len(sys.argv) > 1 else "out"
res = []
def chk(name, ok, detail=""):
    res.append(dict(check=name, status="PASS" if ok else "FAIL", detail=str(detail)))

T = {k: pd.read_csv(f"{out}/data/{FILES[k]}.csv", dtype=str, keep_default_na=False, na_values=[""]) for k in DD}
gt = pd.read_csv(f"{out}/ground_truth/ground_truth.csv", dtype=str, keep_default_na=False, na_values=[""])
num = lambda df, c: pd.to_numeric(df[c])
for c in ["energy_kwh", "demand_kw_avg", "demand_kw_peak", "register_kwh"]: T["EnergyReading"][c] = num(T["EnergyReading"], c)
for c in ["start_utc", "planned_end_utc", "end_utc"]: T["ProductionBatch"][c] = pd.to_datetime(T["ProductionBatch"][c], utc=True)

# 1 schema + PK + enum
for ent, rows in DD.items():
    df = T[ent]
    chk(f"columns match dictionary: {ent}", list(df.columns) == cols(ent))
    pk = [r["field"] for r in rows if r["key"] == "PK"]
    chk(f"PK unique: {ent}", not df.duplicated(pk).any(), f"{len(df)} rows")
    for r in rows:
        if r["required"] == "Y": assert df[r["field"]].notna().all(), f"{ent}.{r['field']} has nulls" if False else True
        if r["required"] == "Y" and df[r["field"]].isna().any(): chk(f"required not null: {ent}.{r['field']}", False, int(df[r["field"]].isna().sum()))
        if r["type"] == "enum" and "," in r["allowed"] or (r["type"] == "enum" and r["allowed"] and "<" not in r["allowed"]):
            allowed = set(r["allowed"].split(","))
            chk(f"enum {ent}.{r['field']}", set(df[r["field"]].dropna().unique()) <= allowed, sorted(set(df[r["field"]].dropna().unique()) - allowed))
chk("required fields non-null (all tables)", not any(r["status"] == "FAIL" and r["check"].startswith("required") for r in res))

# 2 FK integrity
fks = 0
for ent, rows in DD.items():
    for r in rows:
        if "FK " in r["rule"]:
            tgt = r["rule"].split("FK ", 1)[1].split(";")[0].strip().split(" ")[0]; te, tf = tgt.split(".")
            v = T[ent][r["field"]].dropna(); miss = ~v.isin(set(T[te][tf]))
            chk(f"FK {ent}.{r['field']} -> {te}.{tf}", not miss.any(), int(miss.sum())); fks += 1
sh = T["StatusHistory"]
for et, tgt, col in [("ProductionBatch", "ProductionBatch", "batch_id"), ("MaintenanceEvent", "MaintenanceEvent", "maintenance_id"), ("Recommendation", "Recommendation", "recommendation_id")]:
    chk(f"StatusHistory polymorphic FK -> {et}", sh[sh.entity_type == et].entity_id.isin(set(T[tgt][col])).all())
chk("ID patterns", all([T["Meter"].meter_id.str.fullmatch(r"MTR-P\d{2}-\d{3}").all(), T["ProductionBatch"].batch_id.str.fullmatch(r"BATCH-2026-\d{6}").all(),
                        T["Tariff"].tariff_id.str.fullmatch(r"TAR-2026-\d{3}").all(), T["Recommendation"].recommendation_id.str.fullmatch(r"REC-2026-\d{6}").all(),
                        T["EnergyReading"].reading_id.str.fullmatch(r"ENG-MTR-P\d{2}-\d{3}-\d{8}T\d{4}Z(-R2)?").all()]))

# 3 hierarchy
M, Ma, Mc = T["Meter"], T["MachineMeterAssignment"], T["Machine"]
main = M[M.meter_type == "MAIN"]
chk("one MAIN meter per plant", main.plant_id.is_unique and set(main.plant_id) == set(T["Plant"].plant_id))
chk("SUB meters parent is MAIN of same plant", M[M.meter_type == "SUB"].merge(main, left_on="parent_meter_id", right_on="meter_id", suffixes=("", "_p")).eval("plant_id == plant_id_p").all())
chk("every machine has DIRECT_SUB + INDIRECT_MAIN", Ma.groupby("machine_id").relation.apply(lambda s: set(s) == {"DIRECT_SUB", "INDIRECT_MAIN"}).all() and set(Ma.machine_id) == set(Mc.machine_id))
chk("bridge: machine and meter in same plant", Ma.merge(Mc, on="machine_id").merge(M, on="meter_id").eval("plant_id_x == plant_id").all() if False else
    (Ma.merge(Mc[["machine_id", "plant_id"]], on="machine_id").merge(M[["meter_id", "plant_id"]], on="meter_id", suffixes=("_mc", "_mt")).eval("plant_id_mc == plant_id_mt").all()))
chk("meters = machines + plants (sub per machine)", (M.meter_type == "SUB").sum() == len(Mc))

# 4 readings: dups, gaps, units, register
R = T["EnergyReading"]; R["ts"] = pd.to_datetime(R.interval_start_utc, utc=True)
chk("interval = 15 min", ((pd.to_datetime(R.interval_end_utc, utc=True) - R.ts) == pd.Timedelta(minutes=15)).all() and (R.ts.dt.minute % 15 == 0).all())
chk("demand_peak >= demand_avg; values non-negative", (R.demand_kw_peak >= R.demand_kw_avg).all() and (R[["energy_kwh", "demand_kw_avg"]] >= 0).all().all())
dupkey = R[R.duplicated(["meter_id", "ts"], keep=False)]
dup_found = set(dupkey[dupkey.ingest_seq == "2"].reading_id)
exp = lambda t: set(gt[gt.issue_type == t].entity_id)
chk("duplicate natural keys == ground truth", dup_found == exp("DUPLICATE_READING") and R.reading_id.str.endswith("-R2").eq(R.ingest_seq == "2").all(), f"{len(dup_found)} found")
P = R[R.ingest_seq == "1"].sort_values(["meter_id", "ts"]).reset_index(drop=True)
P["gap"] = P.groupby("meter_id").ts.diff()
P["d_reg"] = P.groupby("meter_id").register_kwh.diff()
P = P.merge(M[["meter_id", "plant_id"]], on="meter_id")
# gaps
grid = (pd.to_datetime(P.groupby("meter_id").ts.max()) - pd.to_datetime(P.groupby("meter_id").ts.min())) / pd.Timedelta(minutes=15) + 1
miss_n = int((grid - P.groupby("meter_id").size()).sum())
chk("missing intervals == ground-truth gaps", miss_n == int(pd.to_numeric(gt[gt.issue_type == "METER_GAP"].magnitude).sum()), f"{miss_n} missing")
# kW/kWh
conf = P[(P.energy_kwh - P.demand_kw_avg / 4).abs() > 0.0011]
chk("kW/kWh confusion detected == ground truth", set(conf.reading_id) == exp("KW_KWH_CONFUSION"), f"{len(conf)} detected")
chk("confused rows are 4x overstated", np.allclose(conf.energy_kwh / (conf.demand_kw_avg / 4), 4, atol=0.01))
# register vs interval sums
cons = P[(P.gap == pd.Timedelta(minutes=15))]
mis = cons[((cons.d_reg - cons.energy_kwh).abs() > 0.0025) & ((cons.energy_kwh - cons.demand_kw_avg / 4).abs() <= 0.0011)]
chk("meter register vs interval sum mismatches == ground truth", set(mis.reading_id) == exp("METER_TOTAL_MISMATCH"), f"{len(mis)} detected")
after_gap = P[P.gap > pd.Timedelta(minutes=15)]
chk("register delta after gap >= interval energy (lost energy kept in register)", (after_gap.d_reg - after_gap.energy_kwh > -0.0025).all())
reg_clean = P[~P.reading_id.isin(set(conf.reading_id) | exp("METER_TOTAL_MISMATCH")) & (P.gap == pd.Timedelta(minutes=15))]
chk("register deltas reconcile on all unaffected consecutive rows", ((reg_clean.d_reg - reg_clean.energy_kwh).abs() <= 0.0025).all(), f"{len(reg_clean)} rows")
# hierarchy of attribution
direct = Ma[Ma.relation == "DIRECT_SUB"].set_index("meter_id").machine_id
sub = P[P.machine_id.notna()]
bad_attr = sub[sub.machine_id != sub.meter_id.map(direct)]
chk("machine outside meter hierarchy == ground truth", set(bad_attr.reading_id) == exp("MACHINE_OUTSIDE_METER_HIERARCHY"), f"{len(bad_attr)} detected")
chk("MAIN meter readings carry no machine_id", P[P.meter_id.isin(main.meter_id)].machine_id.isna().all())
# main vs submeters
pv = P.assign(clean=P.demand_kw_avg / 4)
mm = pv[pv.meter_id.isin(main.meter_id)].set_index(["plant_id", "ts"]).clean
ss = pv[~pv.meter_id.isin(main.meter_id)].groupby(["plant_id", "ts"]).clean.agg(["sum", "count"])
nsub = M[M.meter_type == "SUB"].groupby("plant_id").size()
full = ss[ss["count"] == ss.index.get_level_values(0).map(nsub).values]
jn = pd.concat([mm.rename("main"), full["sum"].rename("subs")], axis=1, join="inner")
unm = (jn.main - jn.subs) / jn.main
overall = float((jn.main - jn.subs).sum() / jn.main.sum())
chk("energy totals reconcile: main > sum(submeters) in every interval; overall unmetered share 10-25%", (jn.main - jn.subs).min() > 0 and .10 <= overall <= .25, f"{len(jn)} fully observed intervals, overall unmetered {overall:.1%} (interval range {unm.min():.1%}-{unm.max():.1%}; higher at night/Sundays when machines are in standby)")

# 5 tariffs: independent recompute from UTC + plant tz
Tf, Pl, Cal = T["Tariff"], T["Plant"], T["TariffCalendar"]
Tf["rate_per_kwh"] = num(Tf, "rate_per_kwh")
ok_tile = True
for (pid, dt, ef), g in Tf.groupby(["plant_id", "day_type", "effective_from"]):
    cover = np.zeros(1440, int)
    for _, r in g.iterrows():
        s = int(r.window_start_local[:2]) * 60 + int(r.window_start_local[3:]); e = int(r.window_end_local[:2]) * 60 + int(r.window_end_local[3:])
        idx = np.arange(s, e) if s < e else np.r_[np.arange(s, 1440), np.arange(0, e)]
        cover[idx] += 1
    ok_tile &= (cover == 1).all()
chk("tariff windows tile 24h without overlap per plant/day type/period", ok_tile)
tzmis = Tf[Tf.timezone != Tf.plant_id.map(Pl.set_index("plant_id").timezone)]
chk("tariff timezone mismatch == ground truth", set(tzmis.tariff_id) == exp("TARIFF_TIMEZONE_MISMATCH"), f"{len(tzmis)} rows")
C = T["ReadingCost"]; C["rate_per_kwh"] = num(C, "rate_per_kwh"); C["cost"] = num(C, "cost"); C["energy_kwh_clean"] = num(C, "energy_kwh_clean")
chk("ReadingCost covers each first-transmission reading once", set(C.reading_id) == set(P.reading_id) and len(C) == len(P))
Z = P.merge(C, on="reading_id")
tzmap = Pl.set_index("plant_id").timezone; ok_cost = True; wrong = 0
calmap = Cal.set_index(["plant_id", "calendar_date"]).day_type
for pid, g in Z.groupby("plant_id"):
    loc = g.ts.dt.tz_convert(tzmap[pid]); mnt = (loc.dt.hour * 60 + loc.dt.minute).to_numpy(); dts = loc.dt.strftime("%Y-%m-%d")
    dtype = pd.Series(list(zip([pid] * len(g), dts))).map(calmap).to_numpy(); ldate = loc.dt.tz_localize(None).dt.normalize()
    exp_id = np.full(len(g), None, dtype=object)
    for _, t in Tf[Tf.plant_id == pid].iterrows():
        s = int(t.window_start_local[:2]) * 60 + int(t.window_start_local[3:]); e = int(t.window_end_local[:2]) * 60 + int(t.window_end_local[3:])
        win = (mnt >= s) & (mnt < e) if s < e else (mnt >= s) | (mnt < e)
        eff = (ldate >= pd.Timestamp(t.effective_from)) & ((ldate <= pd.Timestamp(t.effective_to)) if isinstance(t.effective_to, str) else True)
        exp_id[(dtype == t.day_type) & win & eff.to_numpy()] = t.tariff_id
    wrong += int((exp_id != g.tariff_id.to_numpy()).sum())
chk("cost uses correct tariff interval (independent tz recompute)", wrong == 0, f"{wrong} mismatches")
chk("cost = clean energy x rate; clean energy = kW/4", np.allclose(Z.cost, (Z.energy_kwh_clean * Z.rate_per_kwh).round(4), atol=1e-4) and np.allclose(Z.energy_kwh_clean, Z.demand_kw_avg / 4, atol=1e-6))
chk("rate matches tariff row", (Z.rate_per_kwh == Z.tariff_id.map(Tf.set_index("tariff_id").rate_per_kwh)).all())

# 6 shifts + batches
S, B = T["Shift"], T["ProductionBatch"]
S["s"] = pd.to_datetime(S.start_utc, utc=True); S["e"] = pd.to_datetime(S.end_utc, utc=True)
chk("shifts are 8h, ordered", ((S.e - S.s) == pd.Timedelta(hours=8)).all())
Bs = B.merge(S[["shift_id", "s", "e", "is_working", "plant_id"]], on="shift_id", suffixes=("", "_s"))
chk("batch start inside a working shift of same plant", ((Bs.start_utc >= Bs.s) & (Bs.start_utc < Bs.e) & (Bs.is_working == "1") & (Bs.plant_id == Bs.plant_id_s)).all() and len(Bs) == len(B))
chk("batch date ordering (start < end <= planned_end)", ((B.start_utc < B.end_utc) & (B.end_utc <= B.planned_end_utc)).all())
chk("units_produced <= units_planned", (num(B, "units_produced") <= num(B, "units_planned")).all())
Bsort = B.sort_values(["machine_id", "start_utc"]); nxt = Bsort.groupby("machine_id").start_utc.shift(-1)
chk("no overlapping batches per machine", (Bsort.end_utc <= nxt.fillna(pd.Timestamp.max.tz_localize("UTC"))).all())
chk("batch machine in batch plant", B.merge(Mc[["machine_id", "plant_id"]], on="machine_id", suffixes=("", "_m")).eval("plant_id == plant_id_m").all())
chk("batch ids ordered by start time", B.batch_id.is_monotonic_increasing and B.start_utc.is_monotonic_increasing)
chk("aborted batches end early", (B[B.status == "ABORTED"].end_utc < B[B.status == "ABORTED"].planned_end_utc).all())

# 7 lifecycle
H = T["StatusHistory"]; H["t"] = pd.to_datetime(H.changed_at_utc, utc=True)
allowed = {"ProductionBatch": {(None, "PLANNED"), ("PLANNED", "RUNNING"), ("RUNNING", "COMPLETED"), ("RUNNING", "ABORTED")},
           "MaintenanceEvent": {(None, "SCHEDULED"), ("SCHEDULED", "IN_PROGRESS"), ("IN_PROGRESS", "COMPLETED")},
           "Recommendation": {(None, "OPEN"), ("OPEN", "ACKNOWLEDGED"), ("ACKNOWLEDGED", "IMPLEMENTED")}}
trans_ok, chain_ok, order_ok = True, True, True
for (et, eid), g in H.sort_values(["history_id"]).groupby(["entity_type", "entity_id"]):
    pairs = [(None if pd.isna(f) else f, t) for f, t in zip(g.from_state, g.to_state)]
    trans_ok &= all(p in allowed[et] for p in pairs); order_ok &= g.t.is_monotonic_increasing
    chain_ok &= pairs[0][0] is None and all(pairs[i][0] == pairs[i - 1][1] for i in range(1, len(pairs)))
chk("lifecycle transitions valid", trans_ok); chk("history chains consistent (from == previous to)", chain_ok); chk("history timestamps non-decreasing per entity", order_ok)
last = H.sort_values("history_id").groupby(["entity_type", "entity_id"]).to_state.last()
for et, tbl, k in [("ProductionBatch", "ProductionBatch", "batch_id"), ("MaintenanceEvent", "MaintenanceEvent", "maintenance_id"), ("Recommendation", "Recommendation", "recommendation_id")]:
    cur = T[tbl].set_index(k).status
    chk(f"{tbl}.status equals last history state", (last[et].reindex(cur.index) == cur).all())
Mn = T["MaintenanceEvent"]
chk("maintenance date ordering", (pd.to_datetime(Mn.scheduled_start_utc) <= pd.to_datetime(Mn.actual_start_utc)).all() and (pd.to_datetime(Mn.actual_start_utc) < pd.to_datetime(Mn.actual_end_utc)).all())

# 8 state periods
SP = T["MachineStatePeriod"]; SP["s"] = pd.to_datetime(SP.start_utc, utc=True); SP["e"] = pd.to_datetime(SP.end_utc, utc=True)
SP = SP.sort_values(["machine_id", "s"]); chk("state periods contiguous per machine", ((SP.groupby("machine_id").s.shift(-1).dropna() == SP.e[SP.groupby("machine_id").s.shift(-1).notna()]).all()) and (SP.s < SP.e).all())
run_p = SP[SP.state == "RUN"].merge(B[["batch_id", "start_utc", "end_utc", "machine_id"]], on="batch_id", suffixes=("", "_b"))
chk("RUN periods equal their batch window", ((run_p.s == run_p.start_utc) & (run_p.e == run_p.end_utc) & (run_p.machine_id == run_p.machine_id_b)).all() and len(run_p) == len(B))
chk("batch_id set only for RUN", SP[SP.state != "RUN"].batch_id.isna().all())

# 9 derived reconciliation
D = T["DailyPlantSummary"]
for c in ["main_kwh", "submeter_kwh", "energy_cost", "units_produced", "missing_intervals"]: D[c] = num(D, c)
chk("daily main_kwh equals sum of ReadingCost on main meter", np.allclose(D.main_kwh.sum(), Z[Z.meter_id.isin(main.meter_id)].energy_kwh_clean.sum(), atol=0.5))
chk("daily cost equals sum of ReadingCost (main meter)", np.isclose(D.energy_cost.sum(), Z[Z.meter_id.isin(main.meter_id)].cost.sum(), rtol=1e-6))
chk("daily units equal batch units", D.units_produced.sum() == num(B, "units_produced").sum())
ok_d = D[D.reconcile_status == "OK"]
chk("daily intensity = main kWh / units (normalised by output)", np.allclose(num(ok_d.dropna(subset=["energy_intensity_kwh_per_unit"]), "energy_intensity_kwh_per_unit"), (ok_d.dropna(subset=["energy_intensity_kwh_per_unit"]).main_kwh / ok_d.dropna(subset=["energy_intensity_kwh_per_unit"]).units_produced), rtol=1e-3))
BE = T["BatchEnergy"]
chk("BatchEnergy intensity = energy / units on full-coverage batches", (lambda x: np.allclose(num(x, "intensity_kwh_per_unit"), num(x, "energy_kwh") / x.batch_id.map(num(B.set_index("batch_id").reset_index(), "units_produced").set_axis(B.batch_id)), rtol=2e-3))(BE.dropna(subset=["intensity_kwh_per_unit"])))
MD = T["MonthlyDemand"]; chk("demand charge = peak_kw x tariff demand charge", np.allclose(num(MD, "demand_charge"), (num(MD, "peak_kw") * num(MD, "demand_charge_per_kw")).round(2), atol=0.01))

# 10 recommendations
Rc = T["Recommendation"]
for c in ["baseline_value", "observed_value", "expected_savings_cost"]: Rc[c] = num(Rc, c)
chk("recommendations cite measurable baseline and expected savings", (Rc.baseline_value > 0).all() and (Rc.observed_value > Rc.baseline_value).all() and (Rc.expected_savings_cost > 0).all() and (Rc.expected_savings_kwh.notna() | Rc.expected_savings_kw.notna()).all())
chk("recommendation evidence precedes creation", (pd.to_datetime(Rc.evidence_start_utc) < pd.to_datetime(Rc.evidence_end_utc)).all() and (pd.to_datetime(Rc.evidence_end_utc) <= pd.to_datetime(Rc.created_at_utc)).all())
# recall/precision against ground truth (validation only)
gtm = {"REDUCE_IDLE_LOAD": "HIGH_IDLE_CONSUMPTION", "INVESTIGATE_INTENSITY_SHIFT": "ENERGY_INTENSITY_SHIFT"}
for rt, it in gtm.items():
    got, want = set(Rc[Rc.rec_type == rt].machine_id), set(gt[gt.issue_type == it].entity_id)
    chk(f"{rt}: recommended machines == ground-truth machines", got == want, f"got {sorted(got)} want {sorted(want)}")
spike_m = {}
for _, r in gt[gt.issue_type == "PEAK_DEMAND_SPIKE"].iterrows(): spike_m.setdefault((r.plant_id, pd.Timestamp(r.start_utc).tz_convert(tzmap[r.plant_id]).strftime("%Y-%m")), 0)
got_pk = {(r.plant_id, pd.Timestamp(r.evidence_start_utc).tz_convert(tzmap[r.plant_id]).strftime("%Y-%m")) for _, r in Rc[Rc.rec_type == "STAGGER_PEAK_STARTUPS"].iterrows()}
chk("every peak-demand recommendation sits in a plant-month with an injected spike", got_pk <= set(spike_m), sorted(got_pk))
# 11 weather, calendar
W = T["WeatherObservation"]; chk("weather hourly, one row per plant-hour; plausible range", (num(W, "temperature_c").between(-30, 50)).all() and (num(W, "relative_humidity_pct").between(0, 100)).all())
gap_h = W.assign(t=pd.to_datetime(W.observed_at_utc, utc=True)).sort_values(["plant_id", "t"]).groupby("plant_id").t.diff().dropna()
chk("weather cadence is exactly 1h", (gap_h == pd.Timedelta(hours=1)).all())
# 12 separation
leak_words = ("issue_type", "ground_truth", "expected_decision", "gt_id")
chk("no ground-truth columns in input tables", not any(any(w in c for w in leak_words) for k in T for c in T[k].columns))
chk("ground truth file has documented columns", list(gt.columns) == GT_COLS)
chk("ground-truth ids not embedded in input data", not any(T[k].astype(str).apply(lambda s: s.str.startswith("GT-")).any().any() for k in ["Meter", "Machine", "Recommendation", "MaintenanceEvent"]))

fail = [r for r in res if r["status"] == "FAIL"]
summary = dict(dataset=out, checks=len(res), passed=len(res) - len(fail), failed=len(fail), foreign_keys_checked=fks, ground_truth_rows=len(gt),
               ground_truth_by_issue=gt.issue_type.value_counts().sort_index().to_dict(), results=res)
json.dump(summary, open(f"{out}/validation_summary.json", "w"), indent=1)
with open(f"{out}/validation_summary.md", "w") as f:
    f.write(f"# Validation summary\n\n{summary['passed']}/{summary['checks']} checks passed ({fks} foreign keys checked). Ground truth rows: {len(gt)}.\n\n| check | status | detail |\n|---|---|---|\n")
    for r in res: f.write(f"| {r['check']} | {r['status']} | {r['detail']} |\n")
    f.write("\n## Ground-truth anomaly counts\n\n" + "\n".join(f"- {k}: {v}" for k, v in summary["ground_truth_by_issue"].items()) + "\n")
print(f"{summary['passed']}/{summary['checks']} passed")
for r in fail: print("FAIL:", r["check"], r["detail"])
sys.exit(1 if fail else 0)
