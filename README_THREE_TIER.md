# Industrial Energy Intelligence — Three-Tier Application

This application adds a web dashboard to the generated industrial energy dataset.

## Architecture

1. **Presentation tier** — HTML, CSS and JavaScript in `frontend/`.
2. **Application tier** — Flask routes and API endpoints in `backend/`.
3. **Data tier** — SQLite import/query functions in `database/`.

The app imports every CSV in `full_dataset/data/` into a local SQLite database. CSV columns are stored as TEXT so source values are preserved without accidental conversion.

## Setup on Windows PowerShell

Run these commands from `C:\CandidateWorkspace` after extracting this package there:

```powershell
# Activate the Python 3.13 environment
.\.venv313\Scripts\Activate.ps1

# Install Flask
python -m pip install -r requirements.txt

# Start the dashboard
python -m backend.app
```

Open `http://127.0.0.1:5000` in your browser.

## Important folder placement

The folders `backend`, `database`, and `frontend`, plus `requirements.txt`, should be directly inside `CandidateWorkspace`, alongside `generate.py`, `validate.py`, and `full_dataset`.

Expected layout:

```text
CandidateWorkspace/
├── backend/
├── database/
├── frontend/
├── full_dataset/
│   └── data/
├── .venv313/
├── generate.py
├── validate.py
└── requirements.txt
```

## Features

- Loads all CSV files into SQLite.
- Shows table and record counts.
- Displays paginated records for each source table.
- Provides a reload button to rebuild the SQLite database from the CSVs.
- Shows a detected total energy value when a compatible energy column exists.

## API endpoints

- `GET /api/summary`
- `GET /api/tables`
- `GET /api/table/<table_name>?page=1`
- `GET /api/insights`
- `POST /api/reload`

## Notes

The dashboard is an initial data-exploration application. It does not modify the generated source CSVs. The database file is created automatically at `database/energy_project.db`.
