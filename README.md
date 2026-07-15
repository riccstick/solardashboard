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
```

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

This project is pinned to Python 3.9 via `.python-version`.
