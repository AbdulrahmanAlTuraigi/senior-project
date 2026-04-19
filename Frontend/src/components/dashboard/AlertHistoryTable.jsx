import React from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { AlertTriangle, CheckCircle2, History } from "lucide-react";

function fmtSignal(v) {
  return Number.isFinite(v) ? Number(v).toFixed(4) : "--";
}

export default function AlertHistoryTable({ readings }) {
  const alertReadings = (readings || []).filter((r) => r.pipeline_status !== "normal").slice(0, 20);

  const recentNormal = (readings || []).filter((r) => r.pipeline_status === "normal").slice(0, 5);

  const display = [...alertReadings, ...recentNormal]
    .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))
    .slice(0, 15);

  return (
    <Card className="bg-slate-800/50 border-slate-700/50 backdrop-blur">
      <CardContent className="p-6">
        <div className="flex items-center gap-2 mb-4">
          <History className="w-4 h-4 text-slate-400" />
          <h3 className="text-sm font-semibold text-slate-200">Detection History</h3>
          {alertReadings.length > 0 && (
            <Badge className="bg-red-500/15 text-red-400 border-red-500/30 text-[10px] px-2">
              {alertReadings.length} events
            </Badge>
          )}
        </div>

        {display.length === 0 ? (
          <div className="text-center py-8 text-slate-500 text-sm">No detection events yet</div>
        ) : (
          <div className="overflow-x-auto max-h-[350px] overflow-y-auto">
            <Table>
              <TableHeader>
                <TableRow className="border-slate-700/50 hover:bg-transparent">
                  <TableHead className="text-slate-500 text-[10px] uppercase tracking-wider">Status</TableHead>
                  <TableHead className="text-slate-500 text-[10px] uppercase tracking-wider">Prediction</TableHead>
                  <TableHead className="text-slate-500 text-[10px] uppercase tracking-wider">Pressure (KPa)</TableHead>
                  <TableHead className="text-slate-500 text-[10px] uppercase tracking-wider">Confidence</TableHead>
                  <TableHead className="text-slate-500 text-[10px] uppercase tracking-wider">Timestamp</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {display.map((r, i) => {
                  const isLeak = r.pipeline_status === "leak_detected";
                  const isFault = r.pipeline_status === "sensor_fault";

                  const icon = isLeak || isFault ? (
                    <AlertTriangle className={`w-3.5 h-3.5 ${isLeak ? "text-red-400" : "text-amber-400"}`} />
                  ) : (
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                  );

                  const statusText = isFault ? "Fault" : isLeak ? "Leak" : "Normal";
                  const statusColor = isLeak ? "text-red-400" : isFault ? "text-amber-400" : "text-emerald-400";
                  const confColor = isLeak ? "text-red-300" : isFault ? "text-amber-300" : "text-emerald-300";

                  return (
                    <TableRow key={r.id || i} className="border-slate-700/30 hover:bg-slate-700/20">
                      <TableCell>
                        <div className="flex items-center gap-1.5">
                          {icon}
                          <span className={`text-xs font-medium ${statusColor}`}>{statusText}</span>
                        </div>
                      </TableCell>
                      <TableCell>
                        <span className="text-xs text-slate-300 font-mono">{r.label ?? "no_leak"}</span>
                      </TableCell>
                      <TableCell>
                        <span className="text-xs text-slate-300 font-mono">{fmtSignal(r.pressure_kpa)}</span>
                      </TableCell>
                      <TableCell>
                        <span className={`text-xs font-mono font-medium ${confColor}`}>{r.confidence_label ?? "--"}</span>
                      </TableCell>
                      <TableCell>
                        <span className="text-[11px] text-slate-400 font-mono">
                          {r.timestamp ? new Date(r.timestamp).toLocaleString() : "--"}
                        </span>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
