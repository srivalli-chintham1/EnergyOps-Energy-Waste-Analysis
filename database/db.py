import csv
import sqlite3
from pathlib import Path

def _connect(db_path):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn

def initialize_database(data_dir, db_path, rebuild=False):
    data_dir, db_path = Path(data_dir), Path(db_path)
    if not data_dir.exists():
        raise FileNotFoundError(f"CSV directory not found: {data_dir}")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if rebuild and db_path.exists():
        db_path.unlink()
    csv_files = sorted(data_dir.glob("*.csv"))
    if not csv_files:
        raise FileNotFoundError(f"No CSV files found in {data_dir}")
    with _connect(db_path) as conn:
        for csv_path in csv_files:
            with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                if not reader.fieldnames:
                    continue
                columns = reader.fieldnames
                safe_table = csv_path.stem.replace("-", "_")
                quoted_cols = ", ".join('"' + c.replace('"', '""') + '" TEXT' for c in columns)
                conn.execute(f'CREATE TABLE IF NOT EXISTS "{safe_table}" ({quoted_cols})')
                conn.execute(f'DELETE FROM "{safe_table}"')
                placeholders = ", ".join("?" for _ in columns)
                col_names = ", ".join('"' + c.replace('"', '""') + '"' for c in columns)
                sql = f'INSERT INTO "{safe_table}" ({col_names}) VALUES ({placeholders})'
                rows = ([row.get(c, "") for c in columns] for row in reader)
                conn.executemany(sql, rows)
        conn.commit()

def get_table_names(db_path):
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        return [r["name"] for r in rows]

def get_table_preview(db_path, name, page=1, page_size=25):
    allowed = set(get_table_names(db_path))
    if name not in allowed:
        raise ValueError("Unknown table.")
    offset = (page - 1) * page_size
    with _connect(db_path) as conn:
        columns = [r["name"] for r in conn.execute(f'PRAGMA table_info("{name}")')]
        total = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
        rows = conn.execute(f'SELECT * FROM "{name}" LIMIT ? OFFSET ?', (page_size, offset)).fetchall()
        return {"name": name, "columns": columns, "rows": [dict(r) for r in rows],
                "total": total, "page": page, "page_size": page_size}

def get_summary(db_path):
    names = get_table_names(db_path)
    counts = {}
    with _connect(db_path) as conn:
        for name in names:
            counts[name] = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
    return {"table_count": len(names), "record_count": sum(counts.values()),
            "tables": counts}

def get_insights(db_path):
    names = set(get_table_names(db_path))
    result = {"notes": [], "key_tables": {}}
    for name in ["plant", "meter", "machine", "energy_reading", "production_batch",
                 "recommendation", "daily_plant_summary"]:
        if name in names:
            with _connect(db_path) as conn:
                count = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            result["key_tables"][name] = count
    if "energy_reading" in names:
        with _connect(db_path) as conn:
            cols = [r["name"] for r in conn.execute('PRAGMA table_info("energy_reading")')]
            lower = {c.lower(): c for c in cols}
            energy_col = next((lower[k] for k in ["energy_kwh", "consumption_kwh", "kwh"] if k in lower), None)
            if energy_col:
                try:
                    total = conn.execute(
                        f'SELECT SUM(CAST("{energy_col}" AS REAL)) FROM energy_reading'
                    ).fetchone()[0]
                    result["total_energy_kwh"] = round(total or 0, 3)
                except sqlite3.Error:
                    pass
    result["notes"].append("CSV files are loaded into SQLite as text to preserve the source values exactly.")
    result["notes"].append("Use the Data Explorer to inspect the complete source tables.")
    return result
