import React from "react";
import { Card, CardContent } from "@/components/ui/card";
import { AlertTriangle, CheckCircle2, Clock, Activity, Gauge, Tag } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

function fmtSignal(v) {
  return Number.isFinite(v) ? Number(v).toFixed(4) : "--";
}

export default function LeakStatusCard({ latestReading }) {
  if (!latestReading) {
    return (
      <Card className="bg-slate-800/50 border-slate-700/50 backdrop-blur">
        <CardContent className="p-6 text-center text-slate-400">
          <Activity className="w-8 h-8 mx-auto mb-2 animate-pulse" />
          <p className="text-sm">Waiting for stream...</p>
        </CardContent>
      </Card>
    );
  }

  const status = latestReading.pipeline_status;
  const isLeak = status === "leak_detected";
  const isFault = status === "sensor_fault";

  const title = isFault ? "SENSOR FAULT" : isLeak ? "LEAK DETECTED" : "NORMAL";
  const subtitle = isFault ? (latestReading.sensor_fault ?? "unknown") : "Pipeline Status";

  const cardClass = isLeak
    ? "bg-red-950/50 border-red-500/40"
    : isFault
      ? "bg-amber-950/30 border-amber-500/30"
      : "bg-emerald-950/30 border-emerald-500/30";

  const accentText = isLeak ? "text-red-400" : isFault ? "text-amber-400" : "text-emerald-400";

  const iconBoxClass = isLeak
    ? "bg-red-500/20"
    : isFault
      ? "bg-amber-500/20"
      : "bg-emerald-500/20";

  const Icon = isLeak || isFault ? AlertTriangle : CheckCircle2;

  const signalValue = latestReading.signal_value;
  const signalPct = Number.isFinite(signalValue) ? Math.max(0, Math.min(100, Number(signalValue) * 100)) : 0;

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={status}
        initial={{ scale: 0.95, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ duration: 0.3 }}
      >
        <Card className={`border backdrop-blur overflow-hidden relative ${cardClass}`}>
          {isLeak && <div className="absolute inset-0 bg-red-500/5 animate-pulse" />}
          <CardContent className="p-6 relative">
            <div className="flex items-start justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className={`w-12 h-12 rounded-xl ${iconBoxClass} flex items-center justify-center`}>
                  <Icon className={`w-6 h-6 ${accentText}`} />
                </div>
                <div>
                  <p className="text-xs text-slate-400 uppercase tracking-wider font-medium">{subtitle}</p>
                  <p className={`text-xl font-bold tracking-tight ${accentText}`}>{title}</p>
                </div>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-4 mt-4">
              <div className="bg-slate-900/50 rounded-lg p-3">
                <div className="flex items-center gap-1.5 mb-1">
                  <Activity className="w-3 h-3 text-slate-500" />
                  <span className="text-[10px] text-slate-500 uppercase tracking-wider">Confidence</span>
                </div>
                <p className={`text-sm font-mono font-bold ${isLeak ? "text-red-300" : isFault ? "text-amber-300" : "text-emerald-300"}`}>
                  {latestReading.confidence_label ?? "--"}
                </p>
              </div>
              <div className="bg-slate-900/50 rounded-lg p-3">
                <div className="flex items-center gap-1.5 mb-1">
                  <Gauge className="w-3 h-3 text-slate-500" />
                  <span className="text-[10px] text-slate-500 uppercase tracking-wider">Pressure (KPa)</span>
                </div>
                <p className="text-lg font-bold text-slate-200">
                  {Number.isFinite(latestReading.pressure_kpa) ? Number(latestReading.pressure_kpa).toFixed(3) : "--"}
                </p>
              </div>
              <div className="bg-slate-900/50 rounded-lg p-3">
                <div className="flex items-center gap-1.5 mb-1">
                  <Tag className="w-3 h-3 text-slate-500" />
                  <span className="text-[10px] text-slate-500 uppercase tracking-wider">Prediction</span>
                </div>
                <p className="text-sm font-mono font-bold text-slate-200">
                  {latestReading.label ?? "no_leak"}
                </p>
              </div>
            </div>

            <div className="mt-3 text-[11px] text-slate-400 flex items-center gap-1.5">
              <Clock className="w-3 h-3" />
              {latestReading.timestamp ? new Date(latestReading.timestamp).toLocaleString() : "--"}
            </div>

            <div className="mt-4">
              <div className="flex justify-between items-center mb-1">
                <span className="text-[10px] text-slate-500 uppercase tracking-wider">Leak Probability</span>
                <span className="text-xs text-slate-400 font-mono">{fmtSignal(signalValue)}</span>
              </div>
              <div className="h-2 bg-slate-900/80 rounded-full overflow-hidden">
                <motion.div
                  className={`h-full rounded-full ${
                    isLeak
                      ? "bg-gradient-to-r from-red-500 to-red-400"
                      : isFault
                        ? "bg-gradient-to-r from-amber-500 to-amber-400"
                        : "bg-gradient-to-r from-emerald-500 to-teal-400"
                  }`}
                  initial={{ width: 0 }}
                  animate={{ width: `${signalPct}%` }}
                  transition={{ duration: 0.5 }}
                />
              </div>
            </div>
          </CardContent>
        </Card>
      </motion.div>
    </AnimatePresence>
  );
}
