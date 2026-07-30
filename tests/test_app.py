import atexit
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

# Importing app.py normally starts the hardware monitor threads. Simulation mode
# keeps unit tests hermetic and avoids network access.
_IMPORT_TEMP_DIR = tempfile.TemporaryDirectory()
atexit.register(_IMPORT_TEMP_DIR.cleanup)
os.environ["SIMULATION_MODE"] = "true"
os.environ["SIMULATION_DATABASE_PATH"] = str(
    Path(_IMPORT_TEMP_DIR.name) / "import.db"
)

import app as dashboard  # noqa: E402
from scripts import configure as config_wizard  # noqa: E402


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
            dashboard.requests, "get", side_effect=[flow_response, storage_response]
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

    def test_manifest_route_serves_install_metadata(self):
        with dashboard.app.test_client() as client:
            response = client.get("/manifest.webmanifest")
            self.addCleanup(response.close)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/manifest+json")
        manifest = response.get_json()
        self.assertEqual(manifest["name"], "Solar Dashboard")
        self.assertEqual(manifest["display"], "standalone")
        self.assertEqual(manifest["scope"], "/")
        self.assertEqual(
            {icon["sizes"] for icon in manifest["icons"]},
            {"192x192", "512x512"},
        )

    def test_index_advertises_pwa_and_registration_script(self):
        with dashboard.app.test_client() as client:
            response = client.get("/")

        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn('rel="manifest" href="/manifest.webmanifest"', html)
        self.assertIn('rel="apple-touch-icon"', html)
        self.assertIn('name="theme-color"', html)
        self.assertIn('href="/app-assets/pwa.css"', html)
        self.assertIn('src="/app-assets/pwa.js"', html)
        self.assertIn('id="install-app"', html)

    def test_pwa_static_assets_are_available(self):
        assets = (
            ("/app-assets/icons/icon-192.png", "image/png"),
            ("/app-assets/icons/icon-512.png", "image/png"),
            ("/app-assets/icons/apple-touch-icon.png", "image/png"),
            ("/app-assets/offline.html", "text/html"),
            ("/app-assets/pwa.css", "text/css"),
            ("/app-assets/pwa.js", "text/javascript"),
        )

        with dashboard.app.test_client() as client:
            for path, mimetype in assets:
                with self.subTest(path=path):
                    response = client.get(path)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.mimetype, mimetype)
                    response.close()

    def test_service_worker_route_allows_root_scope_and_disables_http_cache(self):
        with dashboard.app.test_client() as client:
            response = client.get("/service-worker.js")
            self.addCleanup(response.close)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/javascript")
        self.assertEqual(response.headers["Service-Worker-Allowed"], "/")
        self.assertIn("no-cache", response.headers["Cache-Control"])
        service_worker = response.get_data(as_text=True)
        self.assertIn('"/app-assets/offline.html"', service_worker)
        self.assertIn('url.pathname === "/data"', service_worker)


class MacLauncherTests(unittest.TestCase):
    def test_launchers_are_executable_and_start_the_dashboard(self):
        project_dir = Path(__file__).parent.parent
        launchers = (
            project_dir / "app_mode" / "macos" / "Start Solar Dashboard.command",
            project_dir
            / "app_mode"
            / "macos"
            / "Start Solar Dashboard Simulation.command",
        )

        for launcher in launchers:
            with self.subTest(launcher=launcher.name):
                self.assertTrue(os.access(launcher, os.X_OK))
                script = launcher.read_text()
                self.assertTrue(script.startswith("#!/bin/zsh"))
                self.assertIn("exec uv run python app.py", script)
                self.assertIn('open "$DASHBOARD_URL"', script)

    def test_simulation_launcher_enables_simulation_only(self):
        project_dir = Path(__file__).parent.parent
        live = (
            project_dir / "app_mode" / "macos" / "Start Solar Dashboard.command"
        ).read_text()
        simulation = (
            project_dir
            / "app_mode"
            / "macos"
            / "Start Solar Dashboard Simulation.command"
        ).read_text()

        self.assertNotIn("SIMULATION_MODE=true", live)
        self.assertIn("export SIMULATION_MODE=true", simulation)

    def test_configuration_launcher_runs_wizard(self):
        launcher = (
            Path(__file__).parent.parent
            / "app_mode"
            / "macos"
            / "Configure Solar Dashboard.command"
        )

        self.assertTrue(os.access(launcher, os.X_OK))
        self.assertIn("uv run python scripts/configure.py", launcher.read_text())


class ConfigurationWizardTests(unittest.TestCase):
    def test_validators_reject_invalid_network_and_price_values(self):
        with self.assertRaises(ValueError):
            config_wizard.validate_host("http://192.168.1.10")
        with self.assertRaises(ValueError):
            config_wizard.validate_non_negative_number("-0.1")
        with self.assertRaises(ValueError):
            config_wizard.validate_port("70000")

        self.assertEqual(config_wizard.validate_host("inverter.local"), "inverter.local")
        self.assertEqual(config_wizard.validate_non_negative_number("0.30"), "0.30")
        self.assertEqual(config_wizard.validate_port("8000"), "8000")

    def test_rendered_configuration_quotes_values_and_never_omits_settings(self):
        content = config_wizard.render_env(
            {
                "FRONIUS_IP": "192.168.1.10",
                "WATTPILOT_PASSWORD": 'secret "value"',
                "CURRENCY_SYMBOL": "€",
            }
        )

        self.assertIn('FRONIUS_IP="192.168.1.10"', content)
        self.assertIn('WATTPILOT_PASSWORD="secret \\"value\\""', content)
        self.assertIn('CURRENCY_SYMBOL="€"', content)
        for setting in config_wizard.SETTING_ORDER:
            self.assertIn(f"{setting}=", content)

    def test_save_creates_backup_before_replacing_existing_configuration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_file = Path(temp_dir) / ".env"
            env_file.write_text('FRONIUS_IP="old"\n')

            backup = config_wizard.save_env(
                env_file, 'FRONIUS_IP="192.168.1.10"\n'
            )

            self.assertIsNotNone(backup)
            self.assertEqual(backup.read_text(), 'FRONIUS_IP="old"\n')
            self.assertEqual(env_file.read_text(), 'FRONIUS_IP="192.168.1.10"\n')


if __name__ == "__main__":
    unittest.main()
