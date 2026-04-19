import React from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Brain, Target, BarChart3, Crosshair, Loader2 } from "lucide-react";

function fmtPct(value) {
  if (!Number.isFinite(value)) return "--";
  return `${(value * 100).toFixed(1)}%`;
}

function MetricBar({ label, value, icon: Icon, color }) {
  const pctValue = Number.isFinite(value) ? Math.max(0, Math.min(100, value * 100)) : 0;
  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-1.5">
          <Icon className={`w-3 h-3 ${color}`} />
          <span className="text-xs text-slate-400">{label}</span>
        </div>
        <span className={`text-sm font-bold font-mono ${color}`}>{fmtPct(value)}</span>
      </div>
      <div className="h-1.5 bg-slate-900/80 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-700 ${
            color.includes("emerald")
              ? "bg-emerald-500"
              : color.includes("blue")
                ? "bg-blue-500"
                : color.includes("amber")
                  ? "bg-amber-500"
                  : "bg-purple-500"
          }`}
          style={{ width: `${pctValue}%` }}
        />
      </div>
    </div>
  );
}

export default function ModelMetricsCard({ metrics, isLoading }) {
  if (isLoading) {
    return (
      <Card className="bg-slate-800/50 border-slate-700/50 backdrop-blur">
        <CardContent className="p-6 flex items-center justify-center h-48">
          <Loader2 className="w-5 h-5 text-slate-500 animate-spin" />
        </CardContent>
      </Card>
    );
  }

  if (!metrics) return null;

  const predictionsText = Number.isFinite(metrics.total_predictions)
    ? Number(metrics.total_predictions).toLocaleString()
    : "--";
  const alertRateText = Number.isFinite(metrics.alert_rate) ? `${(metrics.alert_rate * 100).toFixed(1)}%` : "--";

  return (
    <Card className="bg-slate-800/50 border-slate-700/50 backdrop-blur">
      <CardContent className="p-6">
        <div className="flex items-center justify-between mb-5">
          <div className="flex items-center gap-2">
            <Brain className="w-4 h-4 text-purple-400" />
            <h3 className="text-sm font-semibold text-slate-200">Model Performance</h3>
          </div>
          <span className="text-[10px] text-slate-500 font-mono">{metrics.model_version ?? "--"}</span>
        </div>

        <div className="space-y-4">
          <MetricBar label="Accuracy" value={metrics.accuracy} icon={Target} color="text-emerald-400" />
          <MetricBar label="Precision" value={metrics.precision} icon={Crosshair} color="text-blue-400" />
          <MetricBar label="Recall" value={metrics.recall} icon={BarChart3} color="text-amber-400" />
          <MetricBar label="F1 Score" value={metrics.f1_score} icon={Brain} color="text-purple-400" />
        </div>

        <div className="mt-4 pt-4 border-t border-slate-700/50 grid grid-cols-2 gap-3">
          <div className="bg-slate-900/50 rounded-lg p-2.5">
            <p className="text-[10px] text-slate-500 uppercase tracking-wider">Predictions</p>
            <p className="text-base font-bold text-slate-200 font-mono">{predictionsText}</p>
          </div>
          <div className="bg-slate-900/50 rounded-lg p-2.5">
            <p className="text-[10px] text-slate-500 uppercase tracking-wider">Alert Rate</p>
            <p className="text-base font-bold text-slate-200 font-mono">{alertRateText}</p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
