
from flask import Flask, jsonify, render_template, request
from pathlib import Path

from database.db import (
    initialize_database,
    get_table_names,
    get_table_preview,
    get_summary,
    get_insights
)


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "full_dataset" / "data"
DB_PATH = ROOT / "database" / "energy_project.db"

app = Flask(
    __name__,
    template_folder="../frontend/templates",
    static_folder="../frontend/static"
)

app.config["JSON_SORT_KEYS"] = False


@app.before_request
def ensure_db():
    if not DB_PATH.exists():
        initialize_database(DATA_DIR, DB_PATH)


@app.get("/")
def home():
    return render_template("index.html")


@app.get("/api/summary")
def summary():
    return jsonify(get_summary(DB_PATH))


@app.get("/api/tables")
def tables():
    return jsonify({"tables": get_table_names(DB_PATH)})


@app.get("/api/table/<name>")
def table_data(name):
    try:
        page = max(1, int(request.args.get("page", 1)))
        return jsonify(
            get_table_preview(DB_PATH, name, page=page, page_size=25)
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.get("/api/insights")
def insights():
    return jsonify(get_insights(DB_PATH))


@app.post("/api/reload")
def reload_data():
    initialize_database(DATA_DIR, DB_PATH, rebuild=True)
    return jsonify({"message": "Database rebuilt from CSV files."})


if __name__ == "__main__":
    if not DATA_DIR.exists():
        raise SystemExit(f"Dataset folder not found: {DATA_DIR}")

    initialize_database(DATA_DIR, DB_PATH)

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )