import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

# Importing app.py normally starts the hardware monitor threads. Simulation mode
# keeps unit tests hermetic and avoids network access.
_IMPORT_TEMP_DIR = tempfile.TemporaryDirectory()
os.environ["SIMULATION_MODE"] = "true"
os.environ["SIMULATION_DATABASE_PATH"] = str(
    Path(_IMPORT_TEMP_DIR.name) / "import.db"
)

import app as dashboard  # noqa: E402


class EnergyDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = dashboard.EnergyDatabase(
            Path(self.temp_dir.name) / "energy.db"
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_summary_calculates_energy_percentages_and_value(self):
        values = {
            "used_wh": 10_000,
            "exported_wh": 2_000,
            "imported_wh": 2_500,
            "solar_generated_wh": 9_000,
            "solar_local_wh": 7_000,
            "direct_solar_wh": 5_500,
        }

        with (
            patch.object(dashboard, "ELECTRICITY_PRICE_PER_KWH", 0.30),
            patch.object(dashboard, "FEED_IN_TARIFF_PER_KWH", 0.08),
        ):
            summary = self.database._summary(values)

        self.assertEqual(summary["energy_used_kwh"], 10.0)
        self.assertEqual(summary["energy_exported_kwh"], 2.0)
        self.assertEqual(summary["self_sufficiency_pct"], 75.0)
        self.assertEqual(summary["self_consumption_pct"], 77.8)
        self.assertEqual(summary["estimated_value"], 2.26)

    def test_intervals_are_bucketed_accumulated_and_rolled_up(self):
        now = datetime(2026, 7, 25, 12, 4, 30)
        values = {
            "used_wh": 100,
            "exported_wh": 20,
            "imported_wh": 10,
            "solar_generated_wh": 120,
            "solar_local_wh": 100,
            "direct_solar_wh": 80,
        }
        self.database.add_interval(values, now)
        self.database.add_interval(values, now + timedelta(seconds=20))

        period_24h, _ = self.database.rolling_summaries(
            now=datetime(2026, 7, 25, 12, 5)
        )

        self.assertEqual(period_24h["energy_used_kwh"], 0.2)
        self.assertEqual(period_24h["solar_generated_kwh"], 0.24)
        self.assertEqual(period_24h["self_sufficiency_pct"], 90.0)

    def test_charging_session_tracks_peak_and_closes(self):
        started = datetime(2026, 7, 25, 10)
        self.database.record_charging(
            {
                "status": "Charging",
                "session_energy_kwh": 0.2,
                "power_w": 3_600,
                "mode": "Eco",
                "name": "Garage",
            },
            started,
        )
        self.database.record_charging(
            {
                "status": "Charging",
                "session_energy_kwh": 1.4,
                "power_w": 7_200,
                "mode": "Eco",
                "name": "Garage",
            },
            started + timedelta(minutes=10),
        )
        self.database.record_charging(
            {"status": "Complete", "session_energy_kwh": 1.4, "power_w": 0},
            started + timedelta(minutes=20),
        )

        sessions = self.database.charging_history()

        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["energy_kwh"], 1.4)
        self.assertEqual(sessions[0]["max_power_w"], 7_200)
        self.assertEqual(
            sessions[0]["ended_at"],
            (started + timedelta(minutes=20)).isoformat(),
        )


class DailyEnergyTrackerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = dashboard.EnergyDatabase(
            Path(self.temp_dir.name) / "tracker.db"
        )
        self.tracker = dashboard.DailyEnergyTracker(self.database)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_update_integrates_two_samples_with_trapezoidal_rule(self):
        start = datetime(2026, 7, 25, 12)
        self.tracker.update(-3_600, -1_800, 7_200, -1_800, now=start)

        result = self.tracker.update(
            -3_600, -1_800, 7_200, -1_800, now=start + timedelta(seconds=1)
        )

        self.assertEqual(result["energy_used_today_kwh"], 0.001)
        self.assertEqual(result["energy_exported_today_kwh"], 0.001)
        self.assertEqual(result["solar_generated_today_kwh"], 0.002)
        self.assertEqual(result["direct_solar_today_kwh"], 0.001)
        self.assertEqual(result["self_sufficiency_today_pct"], 100.0)

    def test_update_does_not_estimate_across_long_sample_gap(self):
        start = datetime(2026, 7, 25, 12)
        self.tracker.update(-2_000, 500, 1_500, 0, now=start)

        result = self.tracker.update(
            -2_000, 500, 1_500, 0, now=start + timedelta(seconds=11)
        )

        self.assertEqual(result["energy_used_today_kwh"], 0.0)
        self.assertEqual(result["energy_imported_today_kwh"], 0.0)


class ApiAndRouteTests(unittest.TestCase):
    def test_fetch_data_parses_fronius_responses(self):
        storage_response = Mock()
        storage_response.json.return_value = {
            "Body": {
                "Data": {
                    "0": {
                        "Controller": {
                            "StateOfCharge_Relative": 63.24,
                            "Temperature_Cell": 24.56,
                        }
                    }
                }
            }
        }
        flow_response = Mock()
        flow_response.json.return_value = {
            "Body": {
                "Data": {
                    "Site": {
                        "P_PV": 4100.4,
                        "P_Load": -1250.2,
                        "P_Grid": -800.7,
                        "P_Akku": -2049.5,
                        "rel_SelfConsumption": 80.04,
                    }
                }
            }
        }

        with patch.object(
            dashboard.requests, "get", side_effect=[storage_response, flow_response]
        ) as get:
            result = dashboard.fetch_data()

        self.assertEqual(result["soc"], 63.2)
        self.assertEqual(result["temp"], 24.6)
        self.assertEqual(result["p_pv"], 4100)
        self.assertEqual(result["p_grid"], -801)
        self.assertEqual(get.call_count, 2)
        get.assert_any_call(dashboard.STORAGE_API, timeout=3)
        get.assert_any_call(dashboard.POWERFLOW_API, timeout=3)

    def test_fetch_data_returns_error_when_request_fails(self):
        with patch.object(
            dashboard.requests, "get", side_effect=TimeoutError("offline")
        ):
            result = dashboard.fetch_data()

        self.assertEqual(result, {"error": "offline"})

    def test_format_power_uses_threshold_and_units(self):
        self.assertEqual(dashboard.format_power(14.9), "0 W")
        self.assertEqual(dashboard.format_power(-999), "-999 W")
        self.assertEqual(dashboard.format_power(1_234), "1.23 kW")

    def test_data_route_keeps_signed_watts_and_adds_display_values(self):
        monitor = Mock()
        monitor.snapshot.return_value = {
            "p_pv": 2_500,
            "p_load": -1_250,
            "p_grid": -900,
            "p_batt": -350,
        }

        with (
            patch.object(dashboard, "simulation_monitor", monitor),
            dashboard.app.test_client() as client,
        ):
            response = client.get("/data")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["p_pv_w"], 2_500)
        self.assertEqual(payload["p_pv"], "2.50 kW")
        self.assertEqual(payload["p_grid_w"], -900)
        self.assertEqual(payload["p_grid"], "-900 W")


if __name__ == "__main__":
    unittest.main()
