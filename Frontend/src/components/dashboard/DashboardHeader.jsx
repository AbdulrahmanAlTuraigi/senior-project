import React, { useMemo } from "react";
import { Shield, Wifi, WifiOff, Clock, Power } from "lucide-react";
import { Badge } from "@/components/ui/badge";

export default function DashboardHeader({ isConnected, lastUpdate, updateInterval, sensorStatus, powerState }) {
  const isStale = lastUpdate && Date.now() - new Date(lastUpdate).getTime() > 3000;

  const security = useMemo(() => {
    const proto = typeof window !== "undefined" ? window.location.protocol : "http:";
    return proto === "https:" ? "HTTPS/TLS" : "HTTP (not encrypted)";
  }, []);

  const securityColor = security.startsWith("HTTPS")
    ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
    : "bg-amber-500/10 border-amber-500/30 text-amber-400";

  return (
    <header className="bg-slate-900 border-b border-slate-700/50 px-6 py-4">
      <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center">
            <Shield className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-lg font-semibold text-white tracking-tight">Pipeline Leak Detection</h1>
            <p className="text-xs text-slate-400">AI-Based Acoustic Monitoring System</p>
          </div>
        </div>

        <div className="flex items-center gap-3 flex-wrap">
          <Badge variant="outline" className={`bg-slate-800/50 border-slate-600 text-slate-300 gap-1.5 px-3 py-1 ${securityColor}`}>
            <Shield className="w-3 h-3" />
            <span className="text-xs">{security}</span>
          </Badge>

          <Badge
            variant="outline"
            className={`gap-1.5 px-3 py-1 ${
              isConnected
                ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
                : "bg-red-500/10 border-red-500/30 text-red-400"
            }`}
          >
            {isConnected ? <Wifi className="w-3 h-3" /> : <WifiOff className="w-3 h-3" />}
            <span className="text-xs">{isConnected ? "Stream Active" : "Disconnected"}</span>
          </Badge>

          <Badge
            variant="outline"
            className={`gap-1.5 px-3 py-1 ${
              powerState === "on"
                ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
                : "bg-red-500/10 border-red-500/30 text-red-400"
            }`}
          >
            <Power className="w-3 h-3" />
            <span className="text-xs">Power {powerState === "on" ? "On" : "Off"}</span>
          </Badge>

          <Badge
            variant="outline"
            className={`gap-1.5 px-3 py-1 ${
              sensorStatus === "online"
                ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
                : sensorStatus === "unstable"
                  ? "bg-amber-500/10 border-amber-500/30 text-amber-400"
                  : "bg-red-500/10 border-red-500/30 text-red-400"
            }`}
          >
            <span className="text-xs">Sensor {sensorStatus ?? "offline"}</span>
          </Badge>

          {lastUpdate && (
            <Badge
              variant="outline"
              className={`gap-1.5 px-3 py-1 ${
                isStale
                  ? "bg-amber-500/10 border-amber-500/30 text-amber-400"
                  : "bg-slate-800/50 border-slate-600 text-slate-300"
              }`}
            >
              <Clock className="w-3 h-3" />
              <span className="text-xs">{isStale ? "Stale Data" : `Updated ${updateInterval ? `${updateInterval}ms` : "now"}`}</span>
            </Badge>
          )}
        </div>
      </div>
    </header>
  );
}
