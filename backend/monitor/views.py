from __future__ import annotations

import csv
import json
import time
from pathlib import PurePosixPath

from django.conf import settings
from django.db.models import Avg, Count, Max, Min
from django.http import FileResponse, HttpResponse, JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from .models import Reading
from .services.engine import engine, load_model_metrics


def _reading_to_dict(r: Reading) -> dict[str, object]:
	return {
		"timestamp": r.timestamp.isoformat(),
		"pressure_kpa": r.pressure_kpa,
		"label": r.label,
		"confidence_score_percent": r.confidence_score_percent,
		"sensor_status": r.sensor_status,
		"prediction_probability": r.prediction_probability,
	}


@csrf_exempt
@require_http_methods(["POST"])
def power_on(request):
	engine.start()
	payload = engine.get_latest()
	return JsonResponse(
		{
			"ok": True,
			"power_state": "on",
			"sensor_status": payload.get("sensor_status"),
			"latest": payload,
		}
	)


@csrf_exempt
@require_http_methods(["POST"])
def power_off(request):
	engine.stop()
	payload = engine.get_latest()
	return JsonResponse(
		{
			"ok": True,
			"power_state": "off",
			"sensor_status": payload.get("sensor_status"),
			"latest": payload,
		}
	)


@require_GET
def system_status(request):
	payload = engine.get_latest()
	return JsonResponse(
		{
			"ok": True,
			"power_state": "on" if engine.is_running else "off",
			"sensor_status": payload.get("sensor_status", "offline"),
			"latest": payload,
		}
	)


@require_GET
def live_latest(request):
	payload = engine.get_latest()
	return JsonResponse(payload)


@require_GET
def live_stream(request):
	def generator():
		last_seq = -1
		while True:
			payload = engine.get_latest()
			seq = int(payload.get("seq", 0))
			if seq != last_seq:
				last_seq = seq
				yield f"data: {json.dumps(payload)}\n\n"
			time.sleep(0.1)

	response = StreamingHttpResponse(generator(), content_type="text/event-stream")
	response["Cache-Control"] = "no-cache"
	response["X-Accel-Buffering"] = "no"
	return response


@require_GET
def model_metrics(request):
	metrics = load_model_metrics()
	agg = Reading.objects.aggregate(
		total_predictions=Count("id"),
	)
	total = int(agg.get("total_predictions", 0) or 0)
	leak_count = Reading.objects.filter(label="leak").count()

	metrics["total_predictions"] = total
	metrics["alert_rate"] = (leak_count / total) if total else None
	return JsonResponse(metrics)


@require_GET
def analytics_summary(request):
	agg = Reading.objects.aggregate(
		total_readings=Count("id"),
		avg_pressure_kpa=Avg("pressure_kpa"),
		min_pressure_kpa=Min("pressure_kpa"),
		max_pressure_kpa=Max("pressure_kpa"),
	)
	leak_events = Reading.objects.filter(label="leak").count()

	payload = engine.get_latest()
	return JsonResponse(
		{
			"total_readings": int(agg.get("total_readings", 0) or 0),
			"leak_events": leak_events,
			"avg_pressure_kpa": agg.get("avg_pressure_kpa"),
			"min_pressure_kpa": agg.get("min_pressure_kpa"),
			"max_pressure_kpa": agg.get("max_pressure_kpa"),
			"power_state": "on" if engine.is_running else "off",
			"sensor_status": payload.get("sensor_status", "offline"),
			"latest_timestamp": payload.get("timestamp"),
		}
	)


@require_GET
def analytics_history(request):
	try:
		limit = int(request.GET.get("limit", "300"))
	except ValueError:
		limit = 300
	limit = max(1, min(limit, 5000))

	rows = list(Reading.objects.all().order_by("-timestamp")[:limit])
	rows.reverse()
	return JsonResponse(
		{
			"count": len(rows),
			"items": [_reading_to_dict(r) for r in rows],
		}
	)


@require_GET
def export_csv(request):
	response = HttpResponse(content_type="text/csv")
	response["Content-Disposition"] = 'attachment; filename="pipeguard_readings.csv"'

	writer = csv.writer(response)
	writer.writerow(["pressure_kpa", "label", "confidence_score_percent"])

	for r in Reading.objects.all().order_by("timestamp"):
		writer.writerow([r.pressure_kpa, r.label, r.confidence_score_percent])

	return response


@require_GET
def frontend_index(request, path: str = ""):
	dist = settings.FRONTEND_DIST_DIR
	if not dist.exists():
		return HttpResponse(
			"Frontend build not found. Run: cd Frontend && npm run build",
			status=503,
			content_type="text/plain",
		)

	if path.startswith("api/") or path.startswith("admin/"):
		return HttpResponse(status=404)

	if path and ".." in PurePosixPath(path).parts:
		return HttpResponse(status=404)

	candidate = dist / path
	if path and candidate.is_file():
		return FileResponse(candidate.open("rb"))

	index_file = dist / "index.html"
	return FileResponse(index_file.open("rb"))
