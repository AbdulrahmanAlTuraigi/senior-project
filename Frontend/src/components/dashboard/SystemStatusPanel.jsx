import React, { useMemo } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Server, Clock, Gauge, Shield, Wifi, Database, Activity, Power } from "lucide-react";

function StatusItem({ icon: Icon, label, value, color }) {
  return (
    <div className="flex items-center gap-3 py-2">
      <div className={`w-7 h-7 rounded-lg flex items-center justify-center ${color}`}>
        <Icon className="w-3.5 h-3.5" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-[10px] text-slate-500 uppercase tracking-wider">{label}</p>
        <p className="text-xs font-medium text-slate-200 truncate">{value}</p>
      </div>
    </div>
  );
}

export default function SystemStatusPanel({ isConnected, lastUpdate, updateInterval, readingCount, powerState, sensorStatus }) {
  const isStale = lastUpdate && Date.now() - new Date(lastUpdate).getTime() > 3000;

  const security = useMemo(() => {
    const proto = typeof window !== "undefined" ? window.location.protocol : "http:";
    return proto === "https:" ? "HTTPS/TLS" : "HTTP (not encrypted)";
  }, []);

  const securityColor = security.startsWith("HTTPS")
    ? "bg-emerald-500/20 text-emerald-400"
    : "bg-amber-500/20 text-amber-400";

  return (
    <Card className="bg-slate-800/50 border-slate-700/50 backdrop-blur">
      <CardContent className="p-6">
        <div className="flex items-center gap-2 mb-4">
          <Server className="w-4 h-4 text-slate-400" />
          <h3 className="text-sm font-semibold text-slate-200">System Status</h3>
        </div>

        <div className="space-y-1 divide-y divide-slate-700/30">
          <StatusItem
            icon={Power}
            label="Power"
            value={powerState === "on" ? "ON" : "OFF"}
            color={powerState === "on" ? "bg-emerald-500/20 text-emerald-400" : "bg-red-500/20 text-red-400"}
          />
          <StatusItem
            icon={Activity}
            label="Sensor Health"
            value={sensorStatus ?? "offline"}
            color={
              sensorStatus === "online"
                ? "bg-emerald-500/20 text-emerald-400"
                : sensorStatus === "unstable"
                  ? "bg-amber-500/20 text-amber-400"
                  : "bg-red-500/20 text-red-400"
            }
          />
          <StatusItem
            icon={Wifi}
            label="Stream"
            value={isConnected ? "Active" : "Disconnected"}
            color={isConnected ? "bg-emerald-500/20 text-emerald-400" : "bg-red-500/20 text-red-400"}
          />
          <StatusItem
            icon={Gauge}
            label="Update Interval"
            value={updateInterval ? `${updateInterval}ms (≤2000ms required)` : "N/A"}
            color={updateInterval && updateInterval <= 2000 ? "bg-emerald-500/20 text-emerald-400" : "bg-amber-500/20 text-amber-400"}
          />
          <StatusItem
            icon={Clock}
            label="Last Update"
            value={lastUpdate ? new Date(lastUpdate).toLocaleTimeString() : "Never"}
            color={isStale ? "bg-amber-500/20 text-amber-400" : "bg-blue-500/20 text-blue-400"}
          />
          <StatusItem icon={Shield} label="Security" value={security} color={securityColor} />
          <StatusItem
            icon={Database}
            label="Readings Collected"
            value={readingCount?.toLocaleString() || "0"}
            color="bg-purple-500/20 text-purple-400"
          />
        </div>
      </CardContent>
    </Card>
  );
}
