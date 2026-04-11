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
```

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
