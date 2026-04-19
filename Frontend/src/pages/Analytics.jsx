import React, { useMemo } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceDot,
} from "recharts";
import { Activity, AlertTriangle, Download, Gauge, ShieldCheck } from "lucide-react";

function MetricCard({ label, value, icon: Icon, accentClass }) {
  return (
    <div className="rounded-2xl border border-slate-700/60 bg-slate-900/60 p-5 backdrop-blur">
      <div className="flex items-center justify-between mb-2">
        <p className="text-xs uppercase tracking-wider text-slate-400">{label}</p>
        <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${accentClass}`}>
          <Icon className="w-4 h-4" />
        </div>
      </div>
      <p className="text-2xl font-semibold text-slate-100 font-mono">{value}</p>
    </div>
  );
}

export default function Analytics() {
  const summaryQuery = useQuery({
    queryKey: ["analytics-summary"],
    queryFn: async () => {
      const res = await fetch("/api/analytics/summary", { cache: "no-store" });
      if (!res.ok) throw new Error("Failed to load summary");
      return res.json();
    },
    refetchInterval: 5000,
  });

  const historyQuery = useQuery({
    queryKey: ["analytics-history"],
    queryFn: async () => {
      const res = await fetch("/api/analytics/history?limit=600", { cache: "no-store" });
      if (!res.ok) throw new Error("Failed to load history");
      return res.json();
    },
    refetchInterval: 2500,
  });

  const items = historyQuery.data?.items ?? [];

  const chartData = useMemo(() => {
    return items.map((r) => ({
      time: r.timestamp ? new Date(r.timestamp).toLocaleTimeString() : "--",
      pressure_kpa: Number.isFinite(r.pressure_kpa) ? r.pressure_kpa : null,
      label: r.label,
    }));
  }, [items]);

  const summary = summaryQuery.data ?? {};

  const avgPressure = Number.isFinite(summary.avg_pressure_kpa)
    ? Number(summary.avg_pressure_kpa).toFixed(3)
    : "--";
  const minPressure = Number.isFinite(summary.min_pressure_kpa)
    ? Number(summary.min_pressure_kpa).toFixed(3)
    : "--";
  const maxPressure = Number.isFinite(summary.max_pressure_kpa)
    ? Number(summary.max_pressure_kpa).toFixed(3)
    : "--";

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_20%_0%,#1e293b_0%,#020617_45%,#020617_100%)] text-slate-100">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-8 space-y-6">
        <header className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-teal-300/80 mb-2">Analytics</p>
            <h1 className="text-2xl sm:text-3xl font-semibold tracking-tight">Pressure Analysis & Leak Trend</h1>
            <p className="text-sm text-slate-400 mt-1">Historical sensor behavior, model outputs, and event visibility.</p>
          </div>
          <div className="flex items-center gap-2">
            <a
              href="/api/export/csv"
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-500/20 border border-blue-400/30 text-blue-200 hover:bg-blue-500/30 transition"
            >
              <Download className="w-4 h-4" />
              Export CSV
            </a>
            <Link
              to="/Dashboard"
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-700/60 border border-slate-600 text-slate-100 hover:bg-slate-700 transition"
            >
              Back to Dashboard
            </Link>
          </div>
        </header>

        <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <MetricCard
            label="Total Readings"
            value={(summary.total_readings ?? 0).toLocaleString()}
            icon={Activity}
            accentClass="bg-teal-500/15 text-teal-300"
          />
          <MetricCard
            label="Leak Events"
            value={(summary.leak_events ?? 0).toLocaleString()}
            icon={AlertTriangle}
            accentClass="bg-red-500/15 text-red-300"
          />
          <MetricCard
            label="Average KPa"
            value={avgPressure}
            icon={Gauge}
            accentClass="bg-amber-500/15 text-amber-300"
          />
          <MetricCard
            label="Sensor Status"
            value={(summary.sensor_status ?? "offline").toUpperCase()}
            icon={ShieldCheck}
            accentClass={
              summary.sensor_status === "online"
                ? "bg-emerald-500/15 text-emerald-300"
                : summary.sensor_status === "unstable"
                  ? "bg-amber-500/15 text-amber-300"
                  : "bg-red-500/15 text-red-300"
            }
          />
        </section>

        <section className="rounded-2xl border border-slate-700/60 bg-slate-900/50 p-5 backdrop-blur">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-slate-200">Pressure Curve (KPa)</h2>
            <p className="text-xs text-slate-400">Min {minPressure} · Max {maxPressure}</p>
          </div>

          <div className="h-80">
            {chartData.length === 0 ? (
              <div className="h-full flex items-center justify-center text-slate-500">No data yet. Turn monitoring on from Dashboard.</div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                  <XAxis dataKey="time" tick={{ fill: "#64748b", fontSize: 10 }} interval="preserveStartEnd" tickCount={8} />
                  <YAxis tick={{ fill: "#64748b", fontSize: 10 }} tickCount={6} />
                  <Tooltip
                    contentStyle={{ backgroundColor: "#0f172a", borderColor: "#334155", borderRadius: 12 }}
                    labelStyle={{ color: "#94a3b8" }}
                    formatter={(value) => [`${Number(value).toFixed(3)} KPa`, "Pressure"]}
                  />
                  <Line type="monotone" dataKey="pressure_kpa" stroke="#22d3ee" strokeWidth={2.5} dot={false} />
                  {chartData.map((d, idx) =>
                    d.label === "leak" ? (
                      <ReferenceDot
                        key={`${d.time}-${idx}`}
                        x={d.time}
                        y={d.pressure_kpa}
                        r={3}
                        fill="#f43f5e"
                        stroke="none"
                      />
                    ) : null
                  )}
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
