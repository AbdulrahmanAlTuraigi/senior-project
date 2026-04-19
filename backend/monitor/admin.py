from django.contrib import admin

from .models import Reading


@admin.register(Reading)
class ReadingAdmin(admin.ModelAdmin):
	list_display = (
		"timestamp",
		"pressure_kpa",
		"label",
		"confidence_score_percent",
		"sensor_status",
	)
	list_filter = ("label", "sensor_status")
	search_fields = ("label", "sensor_status")
	ordering = ("-timestamp",)
