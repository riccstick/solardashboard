const SVG_NS = "http://www.w3.org/2000/svg";

const FLOW_PATHS = {
    pvToHub: "M258 258 L310 310",
    houseToHub: "M502 258 L450 310",
    batteryToHub: "M502 502 L450 450",
    gridToHub: "M258 502 L310 450",
};

function reverseLinePath(path) {
    const match = path.match(/^M\s*([\d.]+)\s+([\d.]+)\s+L\s*([\d.]+)\s+([\d.]+)$/);

    if (!match) {
        return path;
    }

    const [, startX, startY, endX, endY] = match;
    return `M${endX} ${endY} L${startX} ${startY}`;
}

function flowCountForPower(power) {
    if (power === 0) {
        return 0;
    }

    return Math.max(1, Math.min(4, Math.round(Math.abs(power) / 2000) + 1));
}

function parsePower(value) {
    if (!value) {
        return 0;
    }

    if (value.includes("kW")) {
        return parseFloat(value) * 1000;
    }

    return parseFloat(value);
}

function formatDisplayPower(power) {
    const absolutePower = Math.abs(power);

    if (absolutePower < 15) {
        return "0 W";
    }

    if (absolutePower >= 1000) {
        return `${(absolutePower / 1000).toFixed(2)} kW`;
    }

    return `${Math.round(absolutePower)} W`;
}

function createAnimatedDots(layer, path, colorClass, count = 3) {
    layer.replaceChildren();

    for (let index = 0; index < count; index += 1) {
        const dot = document.createElementNS(SVG_NS, "circle");
        dot.setAttribute("r", "8");
        dot.setAttribute("class", `flow-dot ${colorClass}`);

        const motion = document.createElementNS(SVG_NS, "animateMotion");
        motion.setAttribute("dur", "2.8s");
        motion.setAttribute("repeatCount", "indefinite");
        motion.setAttribute("begin", `${index * 0.45}s`);
        motion.setAttribute("path", path);

        dot.appendChild(motion);
        layer.appendChild(dot);
    }
}

function setFlow(layerId, active, path, colorClass, count) {
    const layer = document.getElementById(layerId);

    if (!active) {
        layer.replaceChildren();
        return;
    }

    createAnimatedDots(layer, path, colorClass, count);
}

async function updateData() {
    try {
        const response = await fetch("/data");
        const data = await response.json();

        if (data.error) {
            return;
        }

        const pvPower = parsePower(data.p_pv);
        const housePower = parsePower(data.p_load);
        const gridPower = parsePower(data.p_grid);
        const batteryPower = parsePower(data.p_batt);

        document.getElementById("p_pv").innerText = formatDisplayPower(pvPower);
        document.getElementById("p_load").innerText = formatDisplayPower(housePower);
        document.getElementById("p_grid").innerText = formatDisplayPower(gridPower);
        document.getElementById("p_batt").innerText = formatDisplayPower(batteryPower);

        const soc = data.soc;
        document.getElementById("soc").innerText = `${soc}%`;

        const batteryFill = document.getElementById("batteryFill");
        batteryFill.style.height = `${soc}%`;

        if (batteryPower < 0) {
            batteryFill.style.background = "linear-gradient(to top, #55b945, #bfeab7)";
        } else if (batteryPower > 0) {
            batteryFill.style.background = "linear-gradient(to top, #55b945, #bfeab7)";
        } else {
            batteryFill.style.background = "linear-gradient(to top, #ffffff, #ffffff)";
        }

        setFlow("flow-pv", pvPower > 0, FLOW_PATHS.pvToHub, "flow-dot--pv", flowCountForPower(pvPower));
        setFlow("flow-house", housePower > 0, reverseLinePath(FLOW_PATHS.houseToHub), "flow-dot--house", flowCountForPower(housePower));

        if (batteryPower > 0) {
            setFlow("flow-battery", true, FLOW_PATHS.batteryToHub, "flow-dot--battery-discharge", flowCountForPower(batteryPower));
        } else if (batteryPower < 0) {
            setFlow("flow-battery", true, reverseLinePath(FLOW_PATHS.batteryToHub), "flow-dot--battery-charge", flowCountForPower(batteryPower));
        } else {
            setFlow("flow-battery", false);
        }

        if (gridPower > 0) {
            setFlow("flow-grid", true, FLOW_PATHS.gridToHub, "flow-dot--grid-import", flowCountForPower(gridPower));
        } else if (gridPower < 0) {
            setFlow("flow-grid", true, reverseLinePath(FLOW_PATHS.gridToHub), "flow-dot--grid-export", flowCountForPower(gridPower));
        } else {
            setFlow("flow-grid", false);
        }
    } catch (error) {
        console.error(error);
    }
}

window.addEventListener("DOMContentLoaded", () => {
    updateData();
    window.setInterval(updateData, 2000);
});