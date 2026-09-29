from django.conf import settings
from django.db import models
from django.utils import timezone


class LookupLog(models.Model):
    """Audit trail for lookup downloads and answered questions."""

    class Outcome(models.TextChoices):
        DOWNLOADED = "downloaded", "Downloaded"
        ANSWERED = "answered", "Answered"
        FAILED = "failed", "Failed"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lookup_logs",
    )
    category = models.CharField(max_length=64)
    filter_summary = models.TextField(blank=True, default="")
    row_count = models.PositiveIntegerField(default=0)
    outcome = models.CharField(max_length=16, choices=Outcome.choices)
    message = models.TextField(blank=True, default="")
    created = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created"]
        verbose_name = "Lookup log"
        verbose_name_plural = "Lookup logs"
        permissions = [("use_lookup", "Can use lookup")]

    def __str__(self):
        return f"{self.category} {self.outcome} ({self.row_count} rows) by {self.user}"
