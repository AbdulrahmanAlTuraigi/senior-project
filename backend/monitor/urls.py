from django.urls import path, re_path

from . import views

urlpatterns = [
    path("api/system/power-on", views.power_on, name="power_on"),
    path("api/system/power-off", views.power_off, name="power_off"),
    path("api/system/status", views.system_status, name="system_status"),
    path("api/live/latest", views.live_latest, name="live_latest"),
    path("api/live/stream", views.live_stream, name="live_stream"),
    path("api/model-metrics", views.model_metrics, name="model_metrics"),
    path("api/model_metrics", views.model_metrics, name="model_metrics_legacy"),
    path("api/analytics/summary", views.analytics_summary, name="analytics_summary"),
    path("api/analytics/history", views.analytics_history, name="analytics_history"),
    path("api/export/csv", views.export_csv, name="export_csv"),
    re_path(r"^(?P<path>.*)$", views.frontend_index, name="frontend_index"),
]
