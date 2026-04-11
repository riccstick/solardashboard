import os

from flask import Flask, jsonify, render_template
from dotenv import load_dotenv
import requests

load_dotenv()

app = Flask(__name__)

FRONIUS_IP = os.environ.get("FRONIUS_IP", "192.168.1.142")
STORAGE_API = f"http://{FRONIUS_IP}/solar_api/v1/GetStorageRealtimeData.cgi"
POWERFLOW_API = f"http://{FRONIUS_IP}/solar_api/v1/GetPowerFlowRealtimeData.fcgi"


def fetch_data():
    try:
        storage = requests.get(STORAGE_API, timeout=3).json()
        flow = requests.get(POWERFLOW_API, timeout=3).json()

        device_key = list(storage["Body"]["Data"].keys())[0]
        ctrl = storage["Body"]["Data"][device_key]["Controller"]
        site = flow["Body"]["Data"]["Site"]

        return {
            "soc": round(ctrl.get("StateOfCharge_Relative", 0), 1),
            "temp": round(ctrl.get("Temperature_Cell", 0), 1),
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

    d["p_pv"] = format_power(d["p_pv"])
    d["p_load"] = format_power(d["p_load"])
    d["p_grid"] = format_power(d["p_grid"])
    d["p_batt"] = format_power(d["p_batt"])

    return jsonify(d)


if __name__ == "__main__":
    app.run(debug=True)
