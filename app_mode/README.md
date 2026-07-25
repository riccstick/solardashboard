# Optional app mode

This folder contains the convenience layer that makes Solar Dashboard feel like
an installed application. None of it changes inverter collection, energy
calculations, database storage, or the JSON API.

## Progressive Web App

The `pwa/` folder contains:

- the install manifest and app icons;
- the service worker and offline page;
- the browser registration script;
- styles for the install button and offline indicator.

Installation adds Solar Dashboard to the device's app launcher and opens it in
a dedicated window without normal browser tabs or an address bar. The installed
app is still powered by the browser and still requires the Flask server for live
data.

To test installation on the Mac running Flask:

1. Start simulation mode and open `http://localhost:8000`.
2. In Chrome or Edge, select **Install app** or the address-bar install icon.
3. In Safari, select **File → Add to Dock**.
4. Launch **Solar Dashboard** from the Dock, Applications, or Spotlight.

On iPhone or iPad, open the dashboard in Safari and select
**Share → Add to Home Screen**.

Service workers require a secure context. Installation works on `localhost`;
access from another home-network device must use HTTPS. A permanent setup
normally runs Flask continuously on a Raspberry Pi, NAS, or home server behind
a local HTTPS reverse proxy.

Installing the PWA does not keep Flask running, provide live readings when the
server is unavailable, enable remote access outside the home, or publish the
dashboard to an app store.

## Clickable macOS launchers

The `macos/` folder contains three Finder launchers:

- **Configure Solar Dashboard.command** opens the guided `.env` setup wizard.
- **Start Solar Dashboard.command** starts the configured live dashboard.
- **Start Solar Dashboard Simulation.command** starts generated test data.

Double-click a launcher in Finder. It opens Terminal, starts Flask, and opens
`http://127.0.0.1:8000`. Keep the Terminal window open and press `Control-C` to
stop the server.

If macOS opens a launcher in a text editor, right-click it, select
**Open With → Terminal**, and approve the first launch.
