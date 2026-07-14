import os
import json
import threading
from datetime import datetime
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


class DailyEnergyTracker:
    """Integrate realtime power samples into local daily energy totals."""

    def __init__(self, state_file):
        self.state_file = Path(state_file)
        self.lock = threading.Lock()
        self.day = datetime.now().date().isoformat()
        self.used_wh = 0.0
        self.exported_wh = 0.0
        self.last_sample_at = None
        self.last_used_w = None
        self.last_export_w = None
        self.last_saved_at = None
        self._load()

    def _load(self):
        try:
            state = json.loads(self.state_file.read_text())
            if state.get("day") == self.day:
                self.used_wh = max(0.0, float(state.get("used_wh", 0)))
                self.exported_wh = max(0.0, float(state.get("exported_wh", 0)))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass

    def _save(self, now):
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        temporary_file = self.state_file.with_suffix(".tmp")
        temporary_file.write_text(json.dumps({
            "day": self.day,
            "used_wh": self.used_wh,
            "exported_wh": self.exported_wh,
        }))
        temporary_file.replace(self.state_file)
        self.last_saved_at = now

    def update(self, load_w, grid_w, now=None):
        now = now or datetime.now()
        used_w = abs(float(load_w))
        exported_w = max(0.0, -float(grid_w))

        with self.lock:
            today = now.date().isoformat()
            if today != self.day:
                self.day = today
                self.used_wh = 0.0
                self.exported_wh = 0.0
                self.last_sample_at = None

            if self.last_sample_at is not None:
                elapsed_seconds = (now - self.last_sample_at).total_seconds()
                # Do not estimate across long periods where no samples arrived.
                if 0 < elapsed_seconds <= 10:
                    self.used_wh += ((self.last_used_w + used_w) / 2) * elapsed_seconds / 3600
                    self.exported_wh += ((self.last_export_w + exported_w) / 2) * elapsed_seconds / 3600

            self.last_sample_at = now
            self.last_used_w = used_w
            self.last_export_w = exported_w

            if self.last_saved_at is None or (now - self.last_saved_at).total_seconds() >= 30:
                try:
                    self._save(now)
                except OSError:
                    pass

            return {
                "energy_used_today_kwh": round(self.used_wh / 1000, 3),
                "energy_exported_today_kwh": round(self.exported_wh / 1000, 3),
            }


daily_energy = DailyEnergyTracker(ENERGY_STATE_FILE)


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
    d = fetch_data()

    if "error" in d:
        return jsonify(d)

    d.update(daily_energy.update(d["p_load"], d["p_grid"]))

    # Keep signed watt values for flow direction and formatted values for
    # compatibility with existing clients.
    for key in ("p_pv", "p_load", "p_grid", "p_batt"):
        d[f"{key}_w"] = d[key]
        d[key] = format_power(d[key])

    return jsonify(d)


if __name__ == "__main__":
    app.run(debug=True)
