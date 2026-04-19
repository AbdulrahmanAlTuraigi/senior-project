import React, { useMemo } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { Activity } from "lucide-react";

const CustomTooltip = ({ active, payload }) => {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;

  const status = d.status;
  const statusText =
    status === "sensor_fault" ? "⚠ Sensor Fault" : status === "leak_detected" ? "⚠ Leak Detected" : "● Normal";
  const statusColor = status === "leak_detected" ? "text-red-400" : status === "sensor_fault" ? "text-amber-400" : "text-emerald-400";

  const pressure = Number.isFinite(d.pressure_kpa) ? Number(d.pressure_kpa).toFixed(3) : "--";

  return (
    <div className="bg-slate-800 border border-slate-600 rounded-lg p-3 shadow-xl">
      <p className="text-xs text-slate-400 font-mono">{d.time}</p>
      <p className="text-sm font-bold text-white">Pressure: {pressure} KPa</p>
      <p className={`text-xs font-medium ${statusColor}`}>{statusText}</p>
    </div>
  );
};

export default function SignalChart({ readings }) {
  const chartData = useMemo(() => {
    return (readings || []).slice(-60).map((r) => ({
      time: r.timestamp ? new Date(r.timestamp).toLocaleTimeString() : "--",
      pressure_kpa: Number.isFinite(r.pressure_kpa) ? r.pressure_kpa : null,
      status: r.pipeline_status,
    }));
  }, [readings]);

  const yDomain = useMemo(() => {
    const vals = chartData.map((d) => d.pressure_kpa).filter((v) => Number.isFinite(v));
    if (vals.length === 0) {
      return [0, 1];
    }
    const min = Math.min(...vals);
    const max = Math.max(...vals);
    if (Math.abs(max - min) < 1e-9) {
      const pad = Math.max(0.1, Math.abs(max) * 0.05);
      return [min - pad, max + pad];
    }
    const pad = (max - min) * 0.12;
    return [min - pad, max + pad];
  }, [chartData]);

  return (
    <Card className="bg-slate-800/50 border-slate-700/50 backdrop-blur">
      <CardContent className="p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-teal-400" />
            <h3 className="text-sm font-semibold text-slate-200">Live Pressure Stream (KPa)</h3>
          </div>
          <div className="flex items-center gap-3 text-[10px]">
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-teal-400" />
              <span className="text-slate-400">Pressure</span>
            </span>
          </div>
        </div>

        <div className="h-64">
          {chartData.length === 0 ? (
            <div className="h-full flex items-center justify-center text-slate-500 text-sm">
              <Activity className="w-5 h-5 mr-2 animate-pulse" />
              Waiting for signal data...
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="signalGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#14b8a6" stopOpacity={0.3} />
                    <stop offset="100%" stopColor="#14b8a6" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="time" tick={{ fontSize: 10, fill: "#64748b" }} interval="preserveStartEnd" tickCount={6} />
                <YAxis domain={yDomain} tick={{ fontSize: 10, fill: "#64748b" }} tickCount={5} />
                <Tooltip content={<CustomTooltip />} />
                <Area
                  type="monotone"
                  dataKey="pressure_kpa"
                  stroke="#14b8a6"
                  strokeWidth={2}
                  fill="url(#signalGradient)"
                  dot={false}
                  animationDuration={300}
                  connectNulls
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
