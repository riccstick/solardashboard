const SVG_NS = "http://www.w3.org/2000/svg";
const MIN_ACTIVE_POWER_W = 15;

const FLOW_CONFIG = {
    pv: { node: "#pv .circle", track: "track-pv", layer: "flow-pv" },
    house: { node: "#house .circle", track: "track-house", layer: "flow-house" },
    battery: { node: "#battery .circle", track: "track-battery", layer: "flow-battery" },
    grid: { node: "#grid .circle", track: "track-grid", layer: "flow-grid" },
    car: { node: "#car .circle", track: "track-car", layer: "flow-car" },
};

const flowState = new Map();
let flowPaths = {};

function numberFromPower(value) {
    if (typeof value === "number") return Number.isFinite(value) ? value : 0;
    if (typeof value !== "string") return 0;

    const parsed = Number.parseFloat(value);
    if (!Number.isFinite(parsed)) return 0;
    return /kW/i.test(value) ? parsed * 1000 : parsed;
}

function powerFromData(data, key) {
    return numberFromPower(data[`${key}_w`] ?? data[key]);
}

function formatDisplayPower(power) {
    const magnitude = Math.abs(power);
    if (magnitude < MIN_ACTIVE_POWER_W) return "0 W";
    if (magnitude >= 1000) return `${(magnitude / 1000).toFixed(2)} kW`;
    return `${Math.round(magnitude)} W`;
}

function formatEnergy(value) {
    const energy = Number(value);
    return `${Number.isFinite(energy) ? energy.toFixed(2) : "0.00"} kWh`;
}

function formatPercentage(value) {
    const percentage = Number(value);
    return Number.isFinite(percentage) ? `${percentage.toFixed(1)} %` : "-- %";
}

function setPeriodValues(period24h, period7d) {
    if (!period24h || !period7d) return;
    const values = [
        ["energy-used", "energy_used_kwh", formatEnergy],
        ["energy-exported", "energy_exported_kwh", formatEnergy],
        ["energy-imported", "energy_imported_kwh", formatEnergy],
        ["solar-generated", "solar_generated_kwh", formatEnergy],
        ["direct-solar", "direct_solar_kwh", formatEnergy],
        ["self-sufficiency", "self_sufficiency_pct", formatPercentage],
        ["self-consumption", "self_consumption_pct", formatPercentage],
    ];
    values.forEach(([id, key, formatter]) => {
        document.getElementById(`${id}-today`).textContent = formatter(period24h[key]);
        document.getElementById(`${id}-7d`).textContent = `7 days: ${formatter(period7d[key])}`;
    });
}

function updateWattpilot(wattpilot) {
    const configured = Boolean(wattpilot?.configured);
    const charging = configured && wattpilot.connected && wattpilot.status === "Charging"
        && numberFromPower(wattpilot.power_w) >= MIN_ACTIVE_POWER_W;
    const carNode = document.getElementById("car");
    const carTrack = document.getElementById("track-car");
    const energyCard = document.getElementById("wattpilot-energy-card");

    carNode?.classList.toggle("is-visible", charging);
    carTrack?.classList.toggle("is-visible", charging);
    if (energyCard) energyCard.hidden = !configured;
    if (!configured) return { charging: false, power: 0 };

    document.getElementById("wattpilot-energy-today").textContent =
        formatEnergy(wattpilot.energy_today_kwh);
    document.getElementById("wattpilot-energy-7d").textContent =
        `7 days: ${formatEnergy(wattpilot.energy_7d_kwh)}`;
    const power = charging ? numberFromPower(wattpilot.power_w) : 0;
    document.getElementById("p_car").textContent = formatDisplayPower(power);
    return { charging, power };
}

function flowCountForPower(power) {
    return Math.max(1, Math.min(4, Math.ceil(Math.abs(power) / 2000)));
}

function reversePath(path) {
    const points = path.match(/-?\d+(?:\.\d+)?/g);
    if (!points || points.length !== 4) return path;
    return `M ${points[2]} ${points[3]} L ${points[0]} ${points[1]}`;
}

function elementCircleInSvg(element, svgRect, scaleX, scaleY) {
    const rect = element.getBoundingClientRect();
    return {
        x: (rect.left + rect.width / 2 - svgRect.left) * scaleX,
        y: (rect.top + rect.height / 2 - svgRect.top) * scaleY,
        radius: (Math.min(rect.width * scaleX, rect.height * scaleY) / 2) + 8,
    };
}

function pathBetweenCircles(from, to) {
    const dx = to.x - from.x;
    const dy = to.y - from.y;
    const distance = Math.hypot(dx, dy) || 1;
    const ux = dx / distance;
    const uy = dy / distance;
    const start = { x: from.x + ux * from.radius, y: from.y + uy * from.radius };
    const end = { x: to.x - ux * to.radius, y: to.y - uy * to.radius };
    return `M ${start.x.toFixed(1)} ${start.y.toFixed(1)} L ${end.x.toFixed(1)} ${end.y.toFixed(1)}`;
}

function calculateFlowPaths() {
    const svg = document.querySelector(".diagram-flow");
    const hubElement = document.querySelector(".hub-outer");
    if (!svg || !hubElement) return;

    const svgRect = svg.getBoundingClientRect();
    if (!svgRect.width || !svgRect.height) return;

    const viewBox = svg.viewBox.baseVal;
    const scaleX = viewBox.width / svgRect.width;
    const scaleY = viewBox.height / svgRect.height;
    const hub = elementCircleInSvg(hubElement, svgRect, scaleX, scaleY);

    Object.entries(FLOW_CONFIG).forEach(([name, config]) => {
        const nodeElement = document.querySelector(config.node);
        if (!nodeElement) return;
        const node = elementCircleInSvg(nodeElement, svgRect, scaleX, scaleY);
        flowPaths[name] = pathBetweenCircles(node, hub);
        document.getElementById(config.track)?.setAttribute("d", flowPaths[name]);
    });

    // Force active animations to adopt paths recalculated after a resize.
    flowState.clear();
}

function createAnimatedDots(layer, path, colorClass, count) {
    layer.replaceChildren();
    for (let index = 0; index < count; index += 1) {
        const dot = document.createElementNS(SVG_NS, "circle");
        dot.setAttribute("r", "8");
        dot.setAttribute("class", `flow-dot ${colorClass}`);

        const motion = document.createElementNS(SVG_NS, "animateMotion");
        motion.setAttribute("dur", "2.8s");
        motion.setAttribute("repeatCount", "indefinite");
        motion.setAttribute("begin", `${index * 0.55}s`);
        motion.setAttribute("path", path);
        dot.appendChild(motion);
        layer.appendChild(dot);
    }
}

function setFlow(name, active, direction, colorClass, power) {
    const config = FLOW_CONFIG[name];
    const layer = document.getElementById(config.layer);
    const basePath = flowPaths[name];
    if (!layer || !basePath) return;

    const count = active ? flowCountForPower(power) : 0;
    const path = direction === "to-node" ? reversePath(basePath) : basePath;
    const signature = active ? `${path}|${colorClass}|${count}` : "off";
    if (flowState.get(name) === signature) return;

    flowState.set(name, signature);
    if (!active) layer.replaceChildren();
    else createAnimatedDots(layer, path, colorClass, count);
}

function updateClock() {
    const now = new Date();
    document.getElementById("clock-time").textContent = now.toLocaleTimeString([], {
        hour: "2-digit", minute: "2-digit", second: "2-digit",
    });
    document.getElementById("clock-date").textContent = now.toLocaleDateString([], {
        weekday: "long", year: "numeric", month: "long", day: "numeric",
    });
}

async function updateData() {
    try {
        const response = await fetch("/data", { cache: "no-store" });
        if (!response.ok) throw new Error(`Data request failed (${response.status})`);
        const data = await response.json();
        if (data.error) throw new Error(data.error);

        const pvPower = powerFromData(data, "p_pv");
        const housePower = powerFromData(data, "p_load");
        const gridPower = powerFromData(data, "p_grid");
        const batteryPower = powerFromData(data, "p_batt");

        document.getElementById("p_pv").textContent = formatDisplayPower(pvPower);
        document.getElementById("p_load").textContent = formatDisplayPower(housePower);
        document.getElementById("p_grid").textContent = formatDisplayPower(gridPower);
        document.getElementById("p_batt").textContent = formatDisplayPower(batteryPower);

        const soc = Math.max(0, Math.min(100, numberFromPower(data.soc)));
        document.getElementById("soc").textContent = `${soc.toFixed(1).replace(".0", "")}%`;
        document.getElementById("batteryFill").style.height = `${soc}%`;

        const temperature = data.temp === null || data.temp === "" ? Number.NaN : Number(data.temp);
        document.getElementById("battery-temp").textContent = Number.isFinite(temperature)
            ? `${temperature.toFixed(1)} °C`
            : "-- °C";
        setPeriodValues(data.rolling_24h, data.rolling_7d);
        const carCharging = updateWattpilot(data.wattpilot);

        const active = (power) => Math.abs(power) >= MIN_ACTIVE_POWER_W;
        setFlow("pv", active(pvPower), "to-hub", "flow-dot--pv", pvPower);
        setFlow("house", active(housePower), "to-node", "flow-dot--house", housePower);

        // This inverter reports positive P_Akku while discharging and negative
        // P_Akku while charging.
        setFlow("battery", active(batteryPower), batteryPower > 0 ? "to-hub" : "to-node",
            batteryPower > 0 ? "flow-dot--battery-discharge" : "flow-dot--battery-charge", batteryPower);

        // Fronius: positive P_Grid is import; negative is export.
        setFlow("grid", active(gridPower), gridPower > 0 ? "to-hub" : "to-node",
            gridPower > 0 ? "flow-dot--grid-import" : "flow-dot--grid-export", gridPower);
        setFlow("car", carCharging.charging, "to-node", "flow-dot--car", carCharging.power);
    } catch (error) {
        console.error("Could not update dashboard:", error);
    }
}

window.addEventListener("DOMContentLoaded", () => {
    calculateFlowPaths();
    updateClock();
    updateData();
    window.setInterval(updateClock, 1000);
    window.setInterval(updateData, 2000);

    let resizeTimer;
    window.addEventListener("resize", () => {
        window.clearTimeout(resizeTimer);
        resizeTimer = window.setTimeout(() => {
            calculateFlowPaths();
            updateData();
        }, 120);
    });
});
