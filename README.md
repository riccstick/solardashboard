# solardashboard

[![CI](https://github.com/riccstick/solardashboard/actions/workflows/ci.yml/badge.svg)](https://github.com/riccstick/solardashboard/actions/workflows/ci.yml)

Dashboard for solar data from the Fronius API.

This is an independent community project. It is not affiliated with, endorsed
by, or sponsored by Fronius, Wattpilot, Polestar, or Volvo Cars. Product names
are used only to identify compatible equipment.

## Setup

```bash
uv sync
cp .env.example .env
```

## Configuration

Copy `.env.example` to `.env` and set the Fronius inverter IP there.

```bash
FRONIUS_IP=192.168.50.10
ELECTRICITY_PRICE_PER_KWH=0.30
FEED_IN_TARIFF_PER_KWH=0.08
CURRENCY_SYMBOL=€
WATTPILOT_IP=192.168.50.11
WATTPILOT_PASSWORD=your-device-password
DATABASE_PATH=instance/solar_dashboard.db
POLESTAR_EMAIL=your-polestar-id-email
POLESTAR_PASSWORD=your-polestar-id-password
POLESTAR_VIN=your-vehicle-identification-number
SIMULATION_MODE=false
SIMULATION_DATABASE_PATH=instance/simulation.db
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

Polestar settings are optional. When configured, the dashboard fetches the
vehicle battery level and estimated range every ten minutes through the
`unofficial-polestar-api` package. It uses read-only, short-lived cloud polls;
`POLESTAR_VIN` is optional when the account contains only one vehicle.

## Local simulation

Run the complete dashboard without contacting an inverter, Wattpilot, or
Polestar account:

```bash
SIMULATION_MODE=true uv run python app.py
```

Simulation mode cycles through solar surplus, battery charging and discharge,
grid import and export, nighttime consumption, and active Polestar charging.
It uses `instance/simulation.db` by default so test data cannot modify the live
dashboard database. A badge in the header identifies the active scenario.

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

Run the unit tests without requiring live solar hardware:

```bash
uv run python -m unittest discover -v
```

Lint the Python source and tests:

```bash
uv run ruff check .
```

## Python Version

This project is pinned to Python 3.12 via `.python-version` because the maintained
Wattpilot client requires Python 3.12 or newer.

## License and third-party software

The project source is available under the [MIT License](LICENSE). Dependencies,
icons, product names, and unofficial API clients remain subject to their own
licenses and terms; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and
[TRADEMARKS.md](TRADEMARKS.md). Never commit `.env` or Polestar credentials.
