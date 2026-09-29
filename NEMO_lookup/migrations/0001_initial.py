from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="LookupLog",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("category", models.CharField(max_length=64)),
                ("filter_summary", models.TextField(blank=True, default="")),
                ("row_count", models.PositiveIntegerField(default=0)),
                (
                    "outcome",
                    models.CharField(
                        choices=[("downloaded", "Downloaded"), ("answered", "Answered"), ("failed", "Failed")],
                        max_length=16,
                    ),
                ),
                ("message", models.TextField(blank=True, default="")),
                ("created", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="lookup_logs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Lookup log",
                "verbose_name_plural": "Lookup logs",
                "ordering": ["-created"],
                "permissions": [("use_lookup", "Can use lookup")],
            },
        ),
    ]
