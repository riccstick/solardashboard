import os
import json
import asyncio
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, jsonify, render_template
from dotenv import load_dotenv
import requests

load_dotenv()

app = Flask(__name__)

FRONIUS_IP = os.environ.get("FRONIUS_IP", "192.168.1.142")
STORAGE_API = f"http://{FRONIUS_IP}/solar_api/v1/GetStorageRealtimeData.cgi"
POWERFLOW_API = f"http://{FRONIUS_IP}/solar_api/v1/GetPowerFlowRealtimeData.fcgi"
ENERGY_STATE_FILE = Path(app.instance_path) / "daily_energy.json"
DATABASE_FILE = Path(os.environ.get("DATABASE_PATH", Path(app.instance_path) / "solar_dashboard.db"))
ELECTRICITY_PRICE_PER_KWH = float(os.environ.get("ELECTRICITY_PRICE_PER_KWH", "0.30"))
FEED_IN_TARIFF_PER_KWH = float(os.environ.get("FEED_IN_TARIFF_PER_KWH", "0.08"))
CURRENCY_SYMBOL = os.environ.get("CURRENCY_SYMBOL", "€")
WATTPILOT_IP = os.environ.get("WATTPILOT_IP")
WATTPILOT_PASSWORD = os.environ.get("WATTPILOT_PASSWORD")


class EnergyDatabase:
    """Persist daily energy totals and Wattpilot charging sessions in SQLite."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self):
        with self.connect() as connection:
            connection.executescript("""
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS daily_energy (
                    day TEXT PRIMARY KEY,
                    used_wh REAL NOT NULL DEFAULT 0,
                    exported_wh REAL NOT NULL DEFAULT 0,
                    imported_wh REAL NOT NULL DEFAULT 0,
                    solar_generated_wh REAL NOT NULL DEFAULT 0,
                    solar_local_wh REAL NOT NULL DEFAULT 0,
                    direct_solar_wh REAL NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS charging_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    energy_kwh REAL NOT NULL DEFAULT 0,
                    max_power_w INTEGER NOT NULL DEFAULT 0,
                    mode TEXT,
                    charger_name TEXT
                );
                CREATE INDEX IF NOT EXISTS charging_sessions_started_at
                    ON charging_sessions(started_at);
                CREATE TABLE IF NOT EXISTS energy_intervals (
                    bucket_start TEXT PRIMARY KEY,
                    used_wh REAL NOT NULL DEFAULT 0,
                    exported_wh REAL NOT NULL DEFAULT 0,
                    imported_wh REAL NOT NULL DEFAULT 0,
                    solar_generated_wh REAL NOT NULL DEFAULT 0,
                    solar_local_wh REAL NOT NULL DEFAULT 0,
                    direct_solar_wh REAL NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS wattpilot_energy_intervals (
                    bucket_start TEXT PRIMARY KEY,
                    energy_wh REAL NOT NULL DEFAULT 0
                );
            """)

    def load_day(self, day):
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM daily_energy WHERE day = ?", (day,)).fetchone()
            return dict(row) if row else None

    def save_day(self, state, now):
        with self.connect() as connection:
            connection.execute("""
                INSERT INTO daily_energy (
                    day, used_wh, exported_wh, imported_wh, solar_generated_wh,
                    solar_local_wh, direct_solar_wh, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(day) DO UPDATE SET
                    used_wh=excluded.used_wh,
                    exported_wh=excluded.exported_wh,
                    imported_wh=excluded.imported_wh,
                    solar_generated_wh=excluded.solar_generated_wh,
                    solar_local_wh=excluded.solar_local_wh,
                    direct_solar_wh=excluded.direct_solar_wh,
                    updated_at=excluded.updated_at
            """, (
                state["day"], state["used_wh"], state["exported_wh"],
                state["imported_wh"], state["solar_generated_wh"],
                state["solar_local_wh"], state["direct_solar_wh"], now.isoformat(),
            ))

    def add_interval(self, values, now):
        bucket = now.replace(minute=(now.minute // 5) * 5, second=0, microsecond=0)
        with self.connect() as connection:
            connection.execute("""
                INSERT INTO energy_intervals (
                    bucket_start, used_wh, exported_wh, imported_wh,
                    solar_generated_wh, solar_local_wh, direct_solar_wh
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(bucket_start) DO UPDATE SET
                    used_wh=used_wh + excluded.used_wh,
                    exported_wh=exported_wh + excluded.exported_wh,
                    imported_wh=imported_wh + excluded.imported_wh,
                    solar_generated_wh=solar_generated_wh + excluded.solar_generated_wh,
                    solar_local_wh=solar_local_wh + excluded.solar_local_wh,
                    direct_solar_wh=direct_solar_wh + excluded.direct_solar_wh
            """, (
                bucket.isoformat(), values["used_wh"], values["exported_wh"],
                values["imported_wh"], values["solar_generated_wh"],
                values["solar_local_wh"], values["direct_solar_wh"],
            ))

    @staticmethod
    def _summary(values):
        used_wh = float(values.get("used_wh") or 0)
        imported_wh = float(values.get("imported_wh") or 0)
        solar_wh = float(values.get("solar_generated_wh") or 0)
        solar_local_wh = float(values.get("solar_local_wh") or 0)
        exported_wh = float(values.get("exported_wh") or 0)
        self_sufficiency = 100 * (1 - imported_wh / used_wh) if used_wh else None
        self_consumption = 100 * solar_local_wh / solar_wh if solar_wh else None
        return {
            "energy_used_kwh": round(used_wh / 1000, 3),
            "energy_exported_kwh": round(exported_wh / 1000, 3),
            "energy_imported_kwh": round(imported_wh / 1000, 3),
            "solar_generated_kwh": round(solar_wh / 1000, 3),
            "direct_solar_kwh": round(float(values.get("direct_solar_wh") or 0) / 1000, 3),
            "self_sufficiency_pct": round(max(0, min(100, self_sufficiency)), 1)
                if self_sufficiency is not None else None,
            "self_consumption_pct": round(self_consumption, 1)
                if self_consumption is not None else None,
            "estimated_value": round(
                solar_local_wh / 1000 * ELECTRICITY_PRICE_PER_KWH
                + exported_wh / 1000 * FEED_IN_TARIFF_PER_KWH, 2
            ),
        }

    def rolling_summaries(self, now=None):
        now = now or datetime.now()
        cutoff_24h = (now - timedelta(hours=24)).isoformat()
        cutoff_7d = (now.date() - timedelta(days=6)).isoformat()
        columns = """
            COALESCE(SUM(used_wh), 0) AS used_wh,
            COALESCE(SUM(exported_wh), 0) AS exported_wh,
            COALESCE(SUM(imported_wh), 0) AS imported_wh,
            COALESCE(SUM(solar_generated_wh), 0) AS solar_generated_wh,
            COALESCE(SUM(solar_local_wh), 0) AS solar_local_wh,
            COALESCE(SUM(direct_solar_wh), 0) AS direct_solar_wh
        """
        with self.connect() as connection:
            last_24h = connection.execute(
                f"SELECT {columns} FROM energy_intervals WHERE bucket_start >= ?", (cutoff_24h,)
            ).fetchone()
            last_7d = connection.execute(
                f"SELECT {columns} FROM daily_energy WHERE day >= ?", (cutoff_7d,)
            ).fetchone()
        return self._summary(dict(last_24h)), self._summary(dict(last_7d))

    def record_charging(self, snapshot, now):
        with self.connect() as connection:
            session = connection.execute(
                "SELECT id FROM charging_sessions WHERE ended_at IS NULL ORDER BY id DESC LIMIT 1"
            ).fetchone()
            is_charging = snapshot.get("status") == "Charging"
            if is_charging and session is None:
                cursor = connection.execute("""
                    INSERT INTO charging_sessions
                        (started_at, energy_kwh, max_power_w, mode, charger_name)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    now.isoformat(), snapshot.get("session_energy_kwh", 0),
                    snapshot.get("power_w", 0), snapshot.get("mode"), snapshot.get("name"),
                ))
                session_id = cursor.lastrowid
            elif session is not None:
                session_id = session["id"]
            else:
                return

            connection.execute("""
                UPDATE charging_sessions SET
                    energy_kwh = MAX(energy_kwh, ?),
                    max_power_w = MAX(max_power_w, ?),
                    mode = COALESCE(?, mode),
                    ended_at = ?
                WHERE id = ?
            """, (
                snapshot.get("session_energy_kwh", 0), snapshot.get("power_w", 0),
                snapshot.get("mode"), None if is_charging else now.isoformat(), session_id,
            ))

    def add_wattpilot_energy(self, energy_wh, now):
        bucket = now.replace(minute=(now.minute // 5) * 5, second=0, microsecond=0)
        with self.connect() as connection:
            connection.execute("""
                INSERT INTO wattpilot_energy_intervals (bucket_start, energy_wh)
                VALUES (?, ?)
                ON CONFLICT(bucket_start) DO UPDATE SET
                    energy_wh=energy_wh + excluded.energy_wh
            """, (bucket.isoformat(), energy_wh))

    def wattpilot_energy_summary(self, now=None):
        now = now or datetime.now()
        today_start = datetime.combine(now.date(), datetime.min.time()).isoformat()
        week_start = datetime.combine(
            now.date() - timedelta(days=6), datetime.min.time()
        ).isoformat()
        with self.connect() as connection:
            today_wh = connection.execute(
                "SELECT COALESCE(SUM(energy_wh), 0) FROM wattpilot_energy_intervals "
                "WHERE bucket_start >= ?", (today_start,)
            ).fetchone()[0]
            week_wh = connection.execute(
                "SELECT COALESCE(SUM(energy_wh), 0) FROM wattpilot_energy_intervals "
                "WHERE bucket_start >= ?", (week_start,)
            ).fetchone()[0]
        return {
            "energy_today_kwh": round(float(today_wh) / 1000, 3),
            "energy_7d_kwh": round(float(week_wh) / 1000, 3),
        }

    def daily_history(self, limit=365):
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM daily_energy ORDER BY day DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(row) for row in rows]

    def charging_history(self, limit=100):
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM charging_sessions ORDER BY started_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(row) for row in rows]


class WattpilotMonitor:
    """Keep an optional, read-only Wattpilot connection alive in the background."""

    CAR_STATES = {1: "Not connected", 2: "Charging", 3: "Ready", 4: "Complete"}
    MODES = {3: "Standard", 4: "Eco", 5: "Next trip"}

    def __init__(self, host, password, database):
        self.host = host
        self.password = password
        self.database = database
        self.lock = threading.Lock()
        self.last_energy_sample_at = None
        self.last_power_w = 0
        self.data = {"configured": bool(host and password), "connected": False}
        if self.data["configured"]:
            threading.Thread(target=self._run, name="wattpilot-monitor", daemon=True).start()

    def _run(self):
        asyncio.run(self._connection_loop())

    async def _connection_loop(self):
        from wattpilot_api import Wattpilot

        while True:
            charger = Wattpilot(self.host, self.password, connect_timeout=8, init_timeout=8)
            try:
                await charger.connect()
                while charger.connected:
                    snapshot = {
                        "configured": True,
                        "connected": True,
                        "name": charger.name or "Wattpilot",
                        "status": self.CAR_STATES.get(charger.car_connected, "Unknown"),
                        "mode": self.MODES.get(charger.mode, "Unknown"),
                        "power_w": round(float(charger.power or 0) * 1000),
                        "session_energy_kwh": round(float(charger.energy_counter_since_start or 0) / 1000, 3),
                        "total_energy_kwh": round(float(charger.energy_counter_total or 0) / 1000, 1),
                        "current_a": round(sum(float(value or 0) for value in (
                            charger.amps1, charger.amps2, charger.amps3
                        )), 1),
                    }
                    with self.lock:
                        self.data = snapshot
                    now = datetime.now()
                    self._record_energy(snapshot, now)
                    self.database.record_charging(snapshot, now)
                    await asyncio.sleep(1)
            except Exception as error:
                with self.lock:
                    self.data = {
                        "configured": True,
                        "connected": False,
                        "error": str(error),
                    }
            finally:
                try:
                    await charger.disconnect()
                except Exception:
                    pass
            await asyncio.sleep(10)

    def _record_energy(self, snapshot, now):
        power_w = snapshot["power_w"] if snapshot.get("status") == "Charging" else 0
        if self.last_energy_sample_at is not None:
            elapsed = (now - self.last_energy_sample_at).total_seconds()
            if 0 < elapsed <= 10:
                energy_wh = ((self.last_power_w + power_w) / 2) * elapsed / 3600
                if energy_wh > 0:
                    self.database.add_wattpilot_energy(energy_wh, now)
        self.last_energy_sample_at = now
        self.last_power_w = power_w

    def snapshot(self):
        with self.lock:
            snapshot = dict(self.data)
        snapshot.update(self.database.wattpilot_energy_summary())
        return snapshot


class DailyEnergyTracker:
    """Integrate realtime power samples into local daily energy totals."""

    def __init__(self, database, legacy_state_file=None):
        self.database = database
        self.legacy_state_file = Path(legacy_state_file) if legacy_state_file else None
        self.lock = threading.Lock()
        self.day = datetime.now().date().isoformat()
        self.used_wh = 0.0
        self.exported_wh = 0.0
        self.imported_wh = 0.0
        self.solar_generated_wh = 0.0
        self.solar_local_wh = 0.0
        self.direct_solar_wh = 0.0
        self.last_sample_at = None
        self.last_used_w = None
        self.last_export_w = None
        self.last_import_w = None
        self.last_solar_w = None
        self.last_solar_local_w = None
        self.last_direct_solar_w = None
        self.last_saved_at = None
        self._load()

    def _load(self):
        state = self.database.load_day(self.day)
        if state is None and self.legacy_state_file:
            try:
                legacy = json.loads(self.legacy_state_file.read_text())
                if legacy.get("day") == self.day:
                    state = legacy
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                pass

        if state:
            self.used_wh = max(0.0, float(state.get("used_wh", 0)))
            self.exported_wh = max(0.0, float(state.get("exported_wh", 0)))
            self.imported_wh = max(0.0, float(state.get("imported_wh", 0)))
            self.solar_generated_wh = max(0.0, float(state.get("solar_generated_wh", 0)))
            self.solar_local_wh = max(0.0, float(state.get("solar_local_wh", 0)))
            self.direct_solar_wh = max(0.0, float(state.get("direct_solar_wh", 0)))

    def _state(self):
        return {
            "day": self.day,
            "used_wh": self.used_wh,
            "exported_wh": self.exported_wh,
            "imported_wh": self.imported_wh,
            "solar_generated_wh": self.solar_generated_wh,
            "solar_local_wh": self.solar_local_wh,
            "direct_solar_wh": self.direct_solar_wh,
        }

    def _save(self, now):
        self.database.save_day(self._state(), now)
        self.last_saved_at = now

    def update(self, load_w, grid_w, pv_w, battery_w, now=None):
        now = now or datetime.now()
        used_w = abs(float(load_w))
        exported_w = max(0.0, -float(grid_w))
        imported_w = max(0.0, float(grid_w))
        solar_w = max(0.0, float(pv_w))
        battery_charging_w = max(0.0, -float(battery_w))
        solar_local_w = min(solar_w, max(0.0, solar_w - exported_w))
        direct_solar_w = min(used_w, max(0.0, solar_w - exported_w - battery_charging_w))

        with self.lock:
            today = now.date().isoformat()
            if today != self.day:
                self.day = today
                self.used_wh = 0.0
                self.exported_wh = 0.0
                self.imported_wh = 0.0
                self.solar_generated_wh = 0.0
                self.solar_local_wh = 0.0
                self.direct_solar_wh = 0.0
                self.last_sample_at = None

            if self.last_sample_at is not None:
                elapsed_seconds = (now - self.last_sample_at).total_seconds()
                # Do not estimate across long periods where no samples arrived.
                if 0 < elapsed_seconds <= 10:
                    interval = {
                        "used_wh": ((self.last_used_w + used_w) / 2) * elapsed_seconds / 3600,
                        "exported_wh": ((self.last_export_w + exported_w) / 2) * elapsed_seconds / 3600,
                        "imported_wh": ((self.last_import_w + imported_w) / 2) * elapsed_seconds / 3600,
                        "solar_generated_wh": ((self.last_solar_w + solar_w) / 2) * elapsed_seconds / 3600,
                        "solar_local_wh": ((self.last_solar_local_w + solar_local_w) / 2) * elapsed_seconds / 3600,
                        "direct_solar_wh": ((self.last_direct_solar_w + direct_solar_w) / 2) * elapsed_seconds / 3600,
                    }
                    self.used_wh += interval["used_wh"]
                    self.exported_wh += interval["exported_wh"]
                    self.imported_wh += interval["imported_wh"]
                    self.solar_generated_wh += interval["solar_generated_wh"]
                    self.solar_local_wh += interval["solar_local_wh"]
                    self.direct_solar_wh += interval["direct_solar_wh"]
                    try:
                        self.database.add_interval(interval, now)
                    except sqlite3.Error:
                        pass

            self.last_sample_at = now
            self.last_used_w = used_w
            self.last_export_w = exported_w
            self.last_import_w = imported_w
            self.last_solar_w = solar_w
            self.last_solar_local_w = solar_local_w
            self.last_direct_solar_w = direct_solar_w

            if self.last_saved_at is None or (now - self.last_saved_at).total_seconds() >= 30:
                try:
                    self._save(now)
                except (OSError, sqlite3.Error):
                    pass

            self_sufficiency = None
            if self.used_wh > 0:
                self_sufficiency = max(0.0, min(100.0, 100 * (1 - self.imported_wh / self.used_wh)))

            self_consumption = None
            if self.solar_generated_wh > 0:
                self_consumption = 100 * self.solar_local_wh / self.solar_generated_wh

            estimated_value = (
                self.solar_local_wh / 1000 * ELECTRICITY_PRICE_PER_KWH
                + self.exported_wh / 1000 * FEED_IN_TARIFF_PER_KWH
            )

            return {
                "energy_used_today_kwh": round(self.used_wh / 1000, 3),
                "energy_exported_today_kwh": round(self.exported_wh / 1000, 3),
                "energy_imported_today_kwh": round(self.imported_wh / 1000, 3),
                "self_sufficiency_today_pct": round(self_sufficiency, 1) if self_sufficiency is not None else None,
                "solar_generated_today_kwh": round(self.solar_generated_wh / 1000, 3),
                "direct_solar_today_kwh": round(self.direct_solar_wh / 1000, 3),
                "self_consumption_today_pct": round(self_consumption, 1) if self_consumption is not None else None,
                "estimated_value_today": round(estimated_value, 2),
                "currency_symbol": CURRENCY_SYMBOL,
            }


def fetch_data():
    try:
        storage = requests.get(STORAGE_API, timeout=3).json()
        flow = requests.get(POWERFLOW_API, timeout=3).json()

        device_key = list(storage["Body"]["Data"].keys())[0]
        ctrl = storage["Body"]["Data"][device_key]["Controller"]
        site = flow["Body"]["Data"]["Site"]
        cell_temperature = ctrl.get("Temperature_Cell")

        return {
            "soc": round(ctrl.get("StateOfCharge_Relative", 0), 1),
            "temp": round(cell_temperature, 1) if isinstance(cell_temperature, (int, float)) else None,
            "p_pv": round(site.get("P_PV", 0)),
            "p_load": round(site.get("P_Load", 0)),
            "p_grid": round(site.get("P_Grid", 0)),
            "p_batt": round(site.get("P_Akku", 0)),
            "self_use": round(site.get("rel_SelfConsumption", 0), 1),
        }

    except Exception as e:
        return {"error": str(e)}


class SolarMonitor:
    """Collect inverter data continuously, independently of browser polling."""

    def __init__(self, tracker, interval=2):
        self.tracker = tracker
        self.interval = interval
        self.lock = threading.Lock()
        self.data = {"error": "Waiting for the first inverter reading"}
        threading.Thread(target=self._run, name="solar-monitor", daemon=True).start()

    def _run(self):
        while True:
            snapshot = fetch_data()
            if "error" not in snapshot:
                snapshot.update(self.tracker.update(
                    snapshot["p_load"], snapshot["p_grid"],
                    snapshot["p_pv"], snapshot["p_batt"],
                ))
                snapshot["rolling_24h"], snapshot["rolling_7d"] = database.rolling_summaries()
            with self.lock:
                self.data = snapshot
            time.sleep(self.interval)

    def snapshot(self):
        with self.lock:
            return dict(self.data)


database = EnergyDatabase(DATABASE_FILE)
daily_energy = DailyEnergyTracker(database, ENERGY_STATE_FILE)
wattpilot = WattpilotMonitor(WATTPILOT_IP, WATTPILOT_PASSWORD, database)
solar_monitor = SolarMonitor(daily_energy)


def format_power(v):
    if abs(v) < 15:
        return "0 W"
    if abs(v) >= 1000:
        return f"{v/1000:.2f} kW"
    return f"{int(v)} W"

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/data")
def data():
    d = solar_monitor.snapshot()

    if "error" in d:
        return jsonify(d)

    d["wattpilot"] = wattpilot.snapshot()

    # Keep signed watt values for flow direction and formatted values for
    # compatibility with existing clients.
    for key in ("p_pv", "p_load", "p_grid", "p_batt"):
        d[f"{key}_w"] = d[key]
        d[key] = format_power(d[key])

    return jsonify(d)


@app.route("/history/daily")
def daily_history():
    return jsonify(database.daily_history())


@app.route("/history/charging")
def charging_history():
    return jsonify(database.charging_history())


if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
