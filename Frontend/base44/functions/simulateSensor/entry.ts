import { createClientFromRequest } from 'npm:@base44/sdk@0.8.20';

Deno.serve(async (req) => {
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me();
    if (!user) {
      return Response.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const body = await req.json().catch(() => ({}));
    const batchSize = body.batch_size || 5;

    const segments = ["0 m", "250 m", "500 m", "750 m", "1000 m"];
    const readings = [];

    for (let i = 0; i < batchSize; i++) {
      const now = new Date(Date.now() - (batchSize - 1 - i) * 1000);
      const isLeak = Math.random() < 0.15; // ~15% chance of leak
      const baseSignal = isLeak ? 0.6 + Math.random() * 0.35 : 0.1 + Math.random() * 0.35;
      const noise = (Math.random() - 0.5) * 0.08;
      const signalValue = Math.max(0, Math.min(1, baseSignal + noise));
      const confidence = isLeak
        ? 0.82 + Math.random() * 0.17
        : 0.88 + Math.random() * 0.11;

      readings.push({
        timestamp: now.toISOString(),
        signal_value: parseFloat(signalValue.toFixed(4)),
        pipeline_status: isLeak ? "leak_detected" : "normal",
        confidence: parseFloat(confidence.toFixed(4)),
        segment: segments[Math.floor(Math.random() * segments.length)],
        is_alert: isLeak
      });
    }

    const created = await base44.entities.SensorReading.bulkCreate(readings);

    return Response.json({
      success: true,
      count: created.length,
      readings: created
    });
  } catch (error) {
    return Response.json({ error: error.message }, { status: 500 });
  }
});