from django.db import models


class Reading(models.Model):
	LABEL_LEAK = "leak"
	LABEL_NO_LEAK = "no_leak"
	LABEL_CHOICES = [
		(LABEL_LEAK, "Leak"),
		(LABEL_NO_LEAK, "No Leak"),
	]

	STATUS_ONLINE = "online"
	STATUS_OFFLINE = "offline"
	STATUS_UNSTABLE = "unstable"
	STATUS_CHOICES = [
		(STATUS_ONLINE, "Online"),
		(STATUS_OFFLINE, "Offline"),
		(STATUS_UNSTABLE, "Unstable"),
	]

	timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
	pressure_kpa = models.FloatField()
	label = models.CharField(max_length=16, choices=LABEL_CHOICES)
	confidence_score_percent = models.FloatField()
	prediction_probability = models.FloatField(null=True, blank=True)
	sensor_status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_ONLINE)

	class Meta:
		ordering = ["-timestamp"]

	def __str__(self) -> str:
		return (
			f"Reading(ts={self.timestamp.isoformat()}, pressure_kpa={self.pressure_kpa:.3f}, "
			f"label={self.label}, conf={self.confidence_score_percent:.2f})"
		)
