let installPrompt;

const installButton = document.getElementById("install-app");
const connectionStatus = document.getElementById("connection-status");

function updateConnectionStatus() {
    const offline = !navigator.onLine;
    if (connectionStatus) {
        connectionStatus.hidden = !offline;
    }
}

window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    installPrompt = event;
    if (installButton) installButton.hidden = false;
});

installButton?.addEventListener("click", async () => {
    if (!installPrompt) return;
    installButton.hidden = true;
    await installPrompt.prompt();
    installPrompt = undefined;
});

window.addEventListener("appinstalled", () => {
    installPrompt = undefined;
    if (installButton) installButton.hidden = true;
});

window.addEventListener("online", updateConnectionStatus);
window.addEventListener("offline", updateConnectionStatus);
updateConnectionStatus();

if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
        navigator.serviceWorker.register("/service-worker.js").catch((error) => {
            console.error("Could not register service worker:", error);
        });
    });
}
