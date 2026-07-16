# solardashboard

Dashboard for solar data from the Fronius API.

## Setup

```bash
uv sync
cp .env.example .env
```

## Configuration

Copy `.env.example` to `.env` and set the Fronius inverter IP there.

```bash
FRONIUS_IP=192.168.1.142
ELECTRICITY_PRICE_PER_KWH=0.30
FEED_IN_TARIFF_PER_KWH=0.08
CURRENCY_SYMBOL=€
WATTPILOT_IP=192.168.1.100
WATTPILOT_PASSWORD=your-device-password
DATABASE_PATH=instance/solar_dashboard.db
```

The Wattpilot settings are optional. When both are present, the dashboard opens
a read-only local WebSocket connection and displays live car-charging data. Give
the Wattpilot a fixed DHCP lease so its address does not change.

Daily solar totals and Wattpilot charging sessions are stored in the SQLite
database at `instance/solar_dashboard.db`. Collection runs in the background as
long as the application is running; the browser does not need to remain open.
The optional `DATABASE_PATH` setting can place the database elsewhere.

Wattpilot energy delivered to the car is integrated from live charging power
into five-minute buckets. The dashboard shows today's total, the last seven
calendar days, and a live car node only while charging is active.

Stored history is available as JSON at `/history/daily` and
`/history/charging`.

The electricity price is used for solar energy consumed locally, and the
feed-in tariff is used for energy exported to the grid. Adjust both values to
match your contract so the dashboard's estimated daily value is meaningful.

## Structure

```text
.
├── .env.example
├── .python-version
├── app.py
├── pyproject.toml
├── README.md
├── static
│   ├── css
│   │   └── dashboard.css
│   └── js
│       └── dashboard.js
└── templates
	└── index.html
```

## Run

```bash
uv run python app.py
```

## Development

Common `uv` maintenance commands:

```bash
# Recreate the virtual environment from the lockfile
rm -rf .venv
uv sync

# Upgrade dependencies and refresh the lockfile
uv lock --upgrade
uv sync
```

## Python Version

This project is pinned to Python 3.12 via `.python-version` because the maintained
Wattpilot client requires Python 3.12 or newer.
