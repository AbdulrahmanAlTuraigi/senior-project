import { createClientFromRequest } from 'npm:@base44/sdk@0.8.20';

Deno.serve(async (req) => {
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me();
    if (!user) {
      return Response.json({ error: 'Unauthorized' }, { status: 401 });
    }

    // Simulated model metrics - in production these would come from actual ML evaluation
    const metrics = {
      accuracy: 0.872,
      precision: 0.845,
      recall: 0.891,
      f1_score: 0.867,
      model_version: "v2.1.0",
      last_trained: "2026-02-28T10:00:00Z",
      total_predictions: 0,
      detection_threshold: 0.5
    };

    // Get actual counts from recent readings
    const allReadings = await base44.entities.SensorReading.filter({}, '-created_date', 500);
    metrics.total_predictions = allReadings.length;

    const leaks = allReadings.filter(r => r.pipeline_status === 'leak_detected');
    metrics.total_alerts = leaks.length;
    metrics.alert_rate = allReadings.length > 0 
      ? parseFloat((leaks.length / allReadings.length).toFixed(4)) 
      : 0;

    return Response.json(metrics);
  } catch (error) {
    return Response.json({ error: error.message }, { status: 500 });
  }
});