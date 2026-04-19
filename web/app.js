const el = (id) => document.getElementById(id);

const sensor1 = el("sensor1");
const sensor2 = el("sensor2");
const probability = el("probability");
const confidence = el("confidence");
const meterFill = el("meterFill");
const alertLevel = el("alertLevel");
const leakDetected = el("leakDetected");
const sensorHealth = el("sensorHealth");
const lastUpdate = el("lastUpdate");
const mode = el("mode");
const statusBadge = el("statusBadge");
const packetCount = el("packetCount");
const seqNo = el("seqNo");
const sensorDelta = el("sensorDelta");
const streamDot = el("streamDot");

let packets = 0;
let lastSensor1 = null;

function fmt(v, digits = 3) {
  if (v === null || v === undefined || Number.isNaN(v)) return "--";
  return Number(v).toFixed(digits);
}

function fmtSensor(v, digits = 3) {
  const n = Number(v);
  if (!Number.isFinite(n)) return (0).toFixed(digits);
  return n.toFixed(digits);
}

function deltaLabel(current) {
  if (!Number.isFinite(current) || !Number.isFinite(lastSensor1)) {
    lastSensor1 = Number.isFinite(current) ? current : lastSensor1;
    return "--";
  }
  const d = current - lastSensor1;
  lastSensor1 = current;
  if (Math.abs(d) < 1e-9) return "flat";
  if (d > 0) return `up (${d.toFixed(3)})`;
  return `down (${d.toFixed(3)})`;
}

function paint(packet) {
  const s1 = Number(packet.sensor1_V);
  const s2 = Number(packet.sensor2_V);

  sensor1.textContent = fmtSensor(s1);
  sensor2.textContent = fmtSensor(s2);

  if (packet.leak_probability === null || packet.leak_probability === undefined) {
    probability.textContent = "--";
    meterFill.style.width = "0%";
  } else {
    const p = Number(packet.leak_probability);
    probability.textContent = `${(p * 100).toFixed(1)}%`;
    meterFill.style.width = `${Math.max(0, Math.min(100, p * 100))}%`;
  }

  confidence.textContent = `Confidence: ${packet.confidence ?? "--"}`;
  alertLevel.textContent = packet.alert_level ?? "--";
  leakDetected.textContent = packet.leak_detected ? "YES" : "NO";
  sensorHealth.textContent = packet.sensor_health === "fault"
    ? `FAULT (${packet.sensor_fault ?? "unknown"})`
    : "OK";
  lastUpdate.textContent = packet.timestamp ? new Date(packet.timestamp).toLocaleTimeString() : "--";
  mode.textContent = packet.mode ?? "--";
  packets += 1;
  packetCount.textContent = String(packets);
  seqNo.textContent = packet.seq ?? "--";
  sensorDelta.textContent = deltaLabel(s1);

  streamDot.classList.add("pulse");
  setTimeout(() => streamDot.classList.remove("pulse"), 120);

  if (packet.sensor_health === "fault") {
    statusBadge.textContent = `Sensor fault: ${packet.sensor_fault ?? "unknown"}`;
  } else if (packet.mode === "mock" && packet.gpio_error) {
    statusBadge.textContent = `Mock (${packet.gpio_error})`;
  } else {
    statusBadge.textContent =
      packet.status === "ok" ? `Live (seq ${packet.seq ?? "--"})` : packet.status;
  }
}

function connect() {
  const stream = new EventSource("/api/stream");

  stream.onopen = () => {
    statusBadge.textContent = "Connected";
  };

  stream.onmessage = (event) => {
    try {
      const packet = JSON.parse(event.data);
      paint(packet);
    } catch (err) {
      statusBadge.textContent = "Parse error";
    }
  };

  stream.onerror = () => {
    statusBadge.textContent = "Disconnected - retrying";
    stream.close();
    setTimeout(connect, 1500);
  };
}

async function pollLatest() {
  try {
    const res = await fetch("/api/latest", { cache: "no-store" });
    if (!res.ok) return;
    const packet = await res.json();
    paint(packet);
  } catch (err) {
    // Keep silent; stream path may still be healthy.
  }
}

pollLatest();
setInterval(pollLatest, 1000);
connect();
