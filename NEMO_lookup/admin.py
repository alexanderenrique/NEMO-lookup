from django.contrib import admin

from NEMO_lookup.models import LookupLog


@admin.register(LookupLog)
class LookupLogAdmin(admin.ModelAdmin):
    list_display = ("created", "user", "category", "row_count", "outcome")
    list_filter = ("outcome", "category")
    search_fields = ("filter_summary", "message", "user__username")
    readonly_fields = ("user", "category", "filter_summary", "row_count", "outcome", "message", "created")
