import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import DashboardHeader from "@/components/dashboard/DashboardHeader";
import LeakStatusCard from "@/components/dashboard/LeakStatusCard";
import SignalChart from "@/components/dashboard/SignalChart";
import ModelMetricsCard from "@/components/dashboard/ModelMetricsCard";
import AlertHistoryTable from "@/components/dashboard/AlertHistoryTable";
import SystemStatusPanel from "@/components/dashboard/SystemStatusPanel";

function toReading(packet) {
  const sensorStatus = packet?.sensor_status ?? "offline";
  const predictionProbability =
    typeof packet?.prediction_probability === "number" ? packet.prediction_probability : null;
  const pipeline_status =
    sensorStatus !== "online"
      ? "sensor_fault"
      : packet?.label === "leak"
        ? "leak_detected"
        : "normal";

  const confidencePct =
    typeof packet?.confidence_score_percent === "number"
      ? Math.max(0, Math.min(100, packet.confidence_score_percent))
      : null;

  return {
    id: packet?.seq,
    seq: packet?.seq,
    timestamp: packet?.timestamp,

    pipeline_status,
    sensor_health: sensorStatus,
    sensor_fault: sensorStatus === "online" ? null : sensorStatus,

    signal_value: predictionProbability,
    leak_probability: predictionProbability,
    confidence_label: confidencePct == null ? "--" : `${confidencePct.toFixed(1)}%`,
    alert_level: packet?.label === "leak" ? "CRITICAL" : "NONE",
    label: packet?.label ?? "no_leak",

    segment: "Sensor-1",
    is_alert: packet?.label === "leak" || sensorStatus !== "online",

    pressure_kpa: packet?.pressure_kpa ?? null,
    pressure_pa: packet?.pressure_pa ?? null,
    raw_pressure: packet?.raw_pressure ?? null,
  };
}

export default function Dashboard() {
  const [readings, setReadings] = useState([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [updateInterval, setUpdateInterval] = useState(null);
  const [powerState, setPowerState] = useState("off");
  const [sensorStatus, setSensorStatus] = useState("offline");
  const [isPowerBusy, setIsPowerBusy] = useState(false);

  const lastArrivalMsRef = useRef(null);
  const lastSeqRef = useRef(-1);
  const reconnectTimerRef = useRef(null);

  const pushPacket = useCallback((packet) => {
    if (!packet || typeof packet.seq !== "number") return;
    if (packet.seq <= lastSeqRef.current) return;
    lastSeqRef.current = packet.seq;

    const now = Date.now();
    if (lastArrivalMsRef.current != null) {
      setUpdateInterval(now - lastArrivalMsRef.current);
    }
    lastArrivalMsRef.current = now;

    const r = toReading(packet);
    setReadings((prev) => {
      const updated = [...prev, r];
      return updated.slice(-120);
    });
    if (r.timestamp) setLastUpdate(r.timestamp);
    setSensorStatus(r.sensor_health ?? "offline");
    setIsStreaming((r.sensor_health ?? "offline") === "online");
  }, []);

  const fetchLatest = useCallback(async () => {
    const res = await fetch("/api/live/latest", { cache: "no-store" });
    if (!res.ok) return;
    const packet = await res.json();
    pushPacket(packet);
  }, [pushPacket]);

  const refreshSystemStatus = useCallback(async () => {
    const res = await fetch("/api/system/status", { cache: "no-store" });
    if (!res.ok) return;
    const payload = await res.json();
    setPowerState(payload?.power_state ?? "off");
    setSensorStatus(payload?.sensor_status ?? "offline");
    if (payload?.latest) {
      pushPacket(payload.latest);
    }
  }, [pushPacket]);

  const setPower = useCallback(async (targetState) => {
    setIsPowerBusy(true);
    try {
      const endpoint = targetState === "on" ? "/api/system/power-on" : "/api/system/power-off";
      const res = await fetch(endpoint, { method: "POST" });
      if (!res.ok) return;
      const payload = await res.json();
      setPowerState(payload?.power_state ?? targetState);
      setSensorStatus(payload?.sensor_status ?? "offline");
      if (payload?.latest) {
        pushPacket(payload.latest);
      }
    } finally {
      setIsPowerBusy(false);
    }
  }, [pushPacket]);

  // Model metrics from Django backend
  const { data: metrics, isLoading: metricsLoading } = useQuery({
    queryKey: ["modelMetrics"],
    queryFn: async () => {
      const res = await fetch("/api/model-metrics", { cache: "no-store" });
      if (!res.ok) return null;
      return res.json();
    },
    refetchInterval: 15000,
  });

  // Initial load
  useEffect(() => {
    refreshSystemStatus().catch(() => {});
    fetchLatest().catch(() => {});
  }, [fetchLatest, refreshSystemStatus]);

  // SSE stream (primary)
  useEffect(() => {
    let closed = false;
    let stream;

    const connect = () => {
      if (closed) return;
      try {
        stream = new EventSource("/api/live/stream");
      } catch {
        reconnectTimerRef.current = setTimeout(connect, 1500);
        return;
      }

      stream.onopen = () => {
        refreshSystemStatus().catch(() => {});
      };

      stream.onmessage = (event) => {
        try {
          const packet = JSON.parse(event.data);
          pushPacket(packet);
        } catch {
          // Ignore malformed packets
        }
      };

      stream.onerror = () => {
        refreshSystemStatus().catch(() => {});
        try {
          stream?.close();
        } catch {
          // ignore
        }
        reconnectTimerRef.current = setTimeout(connect, 1500);
      };
    };

    connect();

    return () => {
      closed = true;
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      try {
        stream?.close();
      } catch {
        // ignore
      }
    };
  }, [pushPacket, refreshSystemStatus]);

  // Polling fallback (keeps UI alive even if SSE is blocked)
  useEffect(() => {
    const t = setInterval(() => {
      fetchLatest().catch(() => {});
      refreshSystemStatus().catch(() => {});
    }, 1000);
    return () => clearInterval(t);
  }, [fetchLatest, refreshSystemStatus]);

  // Detect stale stream
  useEffect(() => {
    const staleCheck = setInterval(() => {
      if (lastUpdate && Date.now() - new Date(lastUpdate).getTime() > 3000) {
        setIsStreaming(false);
      }
    }, 1000);
    return () => clearInterval(staleCheck);
  }, [lastUpdate]);

  const latestReading = useMemo(() => (readings.length > 0 ? readings[readings.length - 1] : null), [readings]);

  return (
    <div className="min-h-screen bg-slate-950">
      <DashboardHeader
        isConnected={isStreaming}
        lastUpdate={lastUpdate}
        updateInterval={updateInterval}
        sensorStatus={sensorStatus}
        powerState={powerState}
      />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6 space-y-6">
        <div className="flex items-center justify-between bg-slate-800/30 border border-slate-700/30 rounded-xl px-5 py-3 gap-4 flex-wrap">
          <div>
            <p className="text-sm text-slate-300 font-medium">Monitoring Power</p>
            <p className="text-xs text-slate-500">
              Turn monitoring on/off from backend, view live pressure in KPa, and export collected readings.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => setPower("on")}
              disabled={isPowerBusy || powerState === "on"}
              className="px-5 py-2 rounded-lg text-sm font-medium transition-all bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/30 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Turn On
            </button>
            <button
              onClick={() => setPower("off")}
              disabled={isPowerBusy || powerState === "off"}
              className="px-5 py-2 rounded-lg text-sm font-medium transition-all bg-red-500/20 text-red-400 border border-red-500/30 hover:bg-red-500/30 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Turn Off
            </button>
            <a
              href="/api/export/csv"
              className="px-4 py-2 rounded-lg text-sm font-medium transition-all bg-blue-500/20 text-blue-300 border border-blue-500/30 hover:bg-blue-500/30"
            >
              Export CSV
            </a>
            <Link
              to="/Analytics"
              className="px-4 py-2 rounded-lg text-sm font-medium transition-all bg-slate-700/60 text-slate-200 border border-slate-600 hover:bg-slate-700"
            >
              Analytics Page
            </Link>
          </div>
        </div>

        {/* Top Row: Status + Metrics */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-1">
            <LeakStatusCard latestReading={latestReading} />
          </div>
          <div className="lg:col-span-1">
            <ModelMetricsCard metrics={metrics} isLoading={metricsLoading} />
          </div>
          <div className="lg:col-span-1">
            <SystemStatusPanel
              isConnected={isStreaming}
              lastUpdate={lastUpdate}
              updateInterval={updateInterval}
              readingCount={readings.length}
              powerState={powerState}
              sensorStatus={sensorStatus}
            />
          </div>
        </div>

        {/* Chart */}
        <SignalChart readings={readings} />

        {/* Alert History */}
        <AlertHistoryTable readings={readings} />
      </main>
    </div>
  );
}
