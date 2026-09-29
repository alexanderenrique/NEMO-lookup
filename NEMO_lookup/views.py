"""Lookup views: category downloads and guided questions."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.http import HttpResponse
from django.shortcuts import render
from django.utils.html import escapejs
from django.views.decorators.http import require_GET, require_http_methods

from NEMO.models import Tool, User
from NEMO.utilities import format_datetime, queryset_search_filter
from NEMO_lookup.exports import (
    QUALIFICATION_HEADERS,
    RESERVATION_HEADERS,
    ROW_CAP,
    SUMMARY_HEADERS,
    TRAINING_HEADERS,
    USAGE_HEADERS,
    USER_HEADERS,
    completed_hours_summary,
    format_local,
    hours_between,
    latest_usage,
    open_usage_for_tool,
    person_short,
    qualification_for_pair,
    qualification_rows_from_qs,
    qualifications_for_user,
    reservation_rows_from_qs,
    reservations_queryset,
    summary_rows,
    training_rows_from_qs,
    training_sessions_for_pair,
    usage_events_queryset,
    usage_rows_from_qs,
    user_rows_from_qs,
    users_queryset,
    xlsx_response,
)
from NEMO_lookup.forms import (
    PersonDateRangeToolForm,
    PersonOnlyForm,
    PersonToolForm,
    PersonToolOptionalDatesForm,
    ReservationsFilterForm,
    ToolDateRangeForm,
    UsageEventsFilterForm,
    UsersFilterForm,
    filter_summary_from_cleaned,
)
from NEMO_lookup.models import LookupLog

PERM = "lookup.use_lookup"

DOWNLOADS = [
    {
        "slug": "usage-events",
        "title": "Usage events",
        "description": "Tool usage sessions with lab member and project names, filtered by date range.",
        "url_name": "lookup_usage_events",
    },
    {
        "slug": "reservations",
        "title": "Reservations",
        "description": "Reservations with status filters (kept, cancelled, missed).",
        "url_name": "lookup_reservations",
    },
    {
        "slug": "users",
        "title": "Users",
        "description": "User directory with type, roles, access expiration, and projects.",
        "url_name": "lookup_users",
    },
]

QUESTIONS = [
    {
        "slug": "last-use",
        "title": "When did this lab member last use this tool?",
        "description": "Pick a lab member and a tool to see their most recent session.",
        "url_name": "lookup_question_last_use",
    },
    {
        "slug": "tool-hours",
        "title": "How many hours did this tool run in this period?",
        "description": "Pick a tool and a date range for total hours and a breakdown by lab member.",
        "url_name": "lookup_question_tool_hours",
    },
    {
        "slug": "person-hours",
        "title": "How many hours did this lab member use tools in this period?",
        "description": "Pick a lab member and a date range; optionally limit to one tool.",
        "url_name": "lookup_question_person_hours",
    },
    {
        "slug": "qualified-on",
        "title": "When was this lab member qualified on this tool?",
        "description": "Pick a lab member and a tool to see the qualification date and training history.",
        "url_name": "lookup_question_qualified_on",
    },
    {
        "slug": "lifetime-hours",
        "title": "How many hours has this lab member used this tool?",
        "description": "Pick a lab member and a tool. Date range is optional; blank means all time.",
        "url_name": "lookup_question_lifetime_hours",
    },
    {
        "slug": "qualifications",
        "title": "Which tools is this lab member qualified on?",
        "description": "Pick a lab member to list every tool they are qualified on, with level and date.",
        "url_name": "lookup_question_qualifications",
    },
]


def _log(request, category: str, filter_summary: str, row_count: int, outcome: str, message: str = ""):
    LookupLog.objects.create(
        user=request.user if request.user.is_authenticated else None,
        category=category,
        filter_summary=filter_summary,
        row_count=row_count,
        outcome=outcome,
        message=message,
    )


def _too_many(request, count: int) -> bool:
    if count > ROW_CAP:
        messages.error(
            request,
            f"This filter matches {count:,} rows (limit {ROW_CAP:,}). Narrow the filters and try again.",
        )
        return True
    return False


@login_required
@permission_required(PERM, raise_exception=True)
@require_GET
def lookup_picker(request):
    return render(
        request,
        "NEMO_lookup/picker.html",
        {"downloads": DOWNLOADS, "questions": QUESTIONS},
    )


@login_required
@permission_required(PERM, raise_exception=True)
@require_http_methods(["GET", "POST"])
def lookup_usage_events(request):
    form = UsageEventsFilterForm(request.POST or None) if request.method == "POST" else UsageEventsFilterForm.default_previous_month()
    if request.method == "POST" and form.is_valid():
        cleaned = form.cleaned_data
        qs = usage_events_queryset(
            start=cleaned["start"],
            end=cleaned["end"],
            user_type=cleaned.get("user_type"),
            tool=cleaned.get("tool"),
            project=cleaned.get("project"),
        )
        count = qs.count()
        summary = filter_summary_from_cleaned(cleaned)
        if _too_many(request, count):
            _log(request, "usage-events", summary, count, LookupLog.Outcome.FAILED, "row cap")
        else:
            rows = usage_rows_from_qs(qs)
            _log(request, "usage-events", summary, len(rows), LookupLog.Outcome.DOWNLOADED)
            return xlsx_response(
                f"usage_events_{cleaned['start']}_{cleaned['end']}.xlsx",
                {"Usage events": (USAGE_HEADERS, rows)},
            )
    return render(
        request,
        "NEMO_lookup/filters.html",
        {
            "title": "Usage events",
            "form": form,
            "download_label": "Download Excel",
        },
    )


@login_required
@permission_required(PERM, raise_exception=True)
@require_http_methods(["GET", "POST"])
def lookup_reservations(request):
    form = ReservationsFilterForm(request.POST or None) if request.method == "POST" else ReservationsFilterForm.default_previous_month()
    if request.method == "POST" and form.is_valid():
        cleaned = form.cleaned_data
        qs = reservations_queryset(
            start=cleaned["start"],
            end=cleaned["end"],
            status=cleaned.get("status") or "all",
            user_type=cleaned.get("user_type"),
            tool=cleaned.get("tool"),
            project=cleaned.get("project"),
        )
        count = qs.count()
        summary = filter_summary_from_cleaned(cleaned)
        if _too_many(request, count):
            _log(request, "reservations", summary, count, LookupLog.Outcome.FAILED, "row cap")
        else:
            rows = reservation_rows_from_qs(qs)
            _log(request, "reservations", summary, len(rows), LookupLog.Outcome.DOWNLOADED)
            return xlsx_response(
                f"reservations_{cleaned['start']}_{cleaned['end']}.xlsx",
                {"Reservations": (RESERVATION_HEADERS, rows)},
            )
    return render(
        request,
        "NEMO_lookup/filters.html",
        {
            "title": "Reservations",
            "form": form,
            "download_label": "Download Excel",
        },
    )


@login_required
@permission_required(PERM, raise_exception=True)
@require_http_methods(["GET", "POST"])
def lookup_users(request):
    form = UsersFilterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        cleaned = form.cleaned_data
        qs = users_queryset(
            user_type=cleaned.get("user_type"),
            account=cleaned.get("account") or "all",
            role=cleaned.get("role") or "all",
            access=cleaned.get("access") or "any",
        )
        count = qs.count()
        summary = filter_summary_from_cleaned(cleaned)
        if _too_many(request, count):
            _log(request, "users", summary, count, LookupLog.Outcome.FAILED, "row cap")
        else:
            rows = user_rows_from_qs(qs)
            _log(request, "users", summary, len(rows), LookupLog.Outcome.DOWNLOADED)
            return xlsx_response("users.xlsx", {"Users": (USER_HEADERS, rows)})
    elif request.method == "GET":
        form = UsersFilterForm()
    return render(
        request,
        "NEMO_lookup/filters.html",
        {
            "title": "Users",
            "form": form,
            "download_label": "Download Excel",
        },
    )


def _question_description(title: str) -> str:
    for item in QUESTIONS:
        if item["title"] == title:
            return item["description"]
    return ""


def _question_context(title: str, form, *, answer=None, tables=None, download_ready=False):
    return {
        "title": title,
        "description": _question_description(title),
        "form": form,
        "answer": answer,
        "tables": tables or [],
        "download_ready": download_ready,
        "needs_user_search": "user_display" in form.fields,
        "needs_tool_search": "tool_display" in form.fields,
    }


@login_required
@permission_required(PERM, raise_exception=True)
@require_http_methods(["GET", "POST"])
def question_last_use(request):
    title = "When did this lab member last use this tool?"
    form = PersonToolForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if request.POST.get("action") == "download":
            user, tool = form.cleaned_data["user"], form.cleaned_data["tool"]
            event = latest_usage(user, tool)
            rows = usage_rows_from_qs([event] if event else [])
            _log(request, "last-use", filter_summary_from_cleaned(form.cleaned_data), len(rows), LookupLog.Outcome.DOWNLOADED)
            return xlsx_response("last_use.xlsx", {"Usage events": (USAGE_HEADERS, rows)})
        user, tool = form.cleaned_data["user"], form.cleaned_data["tool"]
        event = latest_usage(user, tool)
        if not event:
            answer = f"{person_short(user)} has no usage on {tool.name}."
            tables = []
        elif event.end is None:
            answer = f"{person_short(user)} is using {tool.name} now, since {format_local(event.start)}."
            tables = [{"title": "Latest session", "headers": USAGE_HEADERS, "rows": [usage_rows_from_qs([event])[0]]}]
        else:
            hours = hours_between(event.start, event.end)
            project = event.project.name if event.project_id else "no project"
            answer = (
                f"{person_short(user)} last used {tool.name} on {format_local(event.start)}–{format_local(event.end)} "
                f"({hours} hours), project {project}."
            )
            tables = [{"title": "Latest session", "headers": USAGE_HEADERS, "rows": [usage_rows_from_qs([event])[0]]}]
        _log(request, "last-use", filter_summary_from_cleaned(form.cleaned_data), 1 if event else 0, LookupLog.Outcome.ANSWERED, answer)
        return render(
            request,
            "NEMO_lookup/question.html",
            _question_context(title, form, answer=answer, tables=tables, download_ready=bool(event)),
        )
    return render(request, "NEMO_lookup/question.html", _question_context(title, form or PersonToolForm()))


@login_required
@permission_required(PERM, raise_exception=True)
@require_http_methods(["GET", "POST"])
def question_tool_hours(request):
    title = "How many hours did this tool run in this period?"
    form = ToolDateRangeForm(request.POST or None) if request.method == "POST" else ToolDateRangeForm.default_previous_month()
    if request.method == "POST" and form.is_valid():
        tool = form.cleaned_data["tool"]
        start, end = form.cleaned_data["start"], form.cleaned_data["end"]
        qs = usage_events_queryset(start=start, end=end, tool=tool, completed_only=True, end_in_range=True)
        summary = completed_hours_summary(qs, group_by="user")
        open_event = open_usage_for_tool(tool)
        if request.POST.get("action") == "download":
            sheets = {
                "By lab member": (SUMMARY_HEADERS, summary_rows(summary.breakdown)),
                "Sessions": (USAGE_HEADERS, usage_rows_from_qs(summary.sessions)),
            }
            _log(
                request,
                "tool-hours",
                filter_summary_from_cleaned(form.cleaned_data),
                summary.session_count,
                LookupLog.Outcome.DOWNLOADED,
            )
            return xlsx_response(f"tool_hours_{tool.name}_{start}_{end}.xlsx", sheets)
        answer = (
            f"{tool.name} ran {summary.total_hours} hours across {summary.session_count} sessions "
            f"from {start.isoformat()} to {end.isoformat()}."
        )
        if open_event:
            answer += (
                f" {person_short(open_event.user)} is using it now (since {format_local(open_event.start)}); "
                "that session is not included in the total."
            )
        tables = [
            {"title": "By lab member", "headers": SUMMARY_HEADERS, "rows": summary_rows(summary.breakdown)},
            {"title": "Sessions", "headers": USAGE_HEADERS, "rows": usage_rows_from_qs(summary.sessions)},
        ]
        _log(request, "tool-hours", filter_summary_from_cleaned(form.cleaned_data), summary.session_count, LookupLog.Outcome.ANSWERED, answer)
        return render(
            request,
            "NEMO_lookup/question.html",
            _question_context(title, form, answer=answer, tables=tables, download_ready=True),
        )
    return render(request, "NEMO_lookup/question.html", _question_context(title, form))


@login_required
@permission_required(PERM, raise_exception=True)
@require_http_methods(["GET", "POST"])
def question_person_hours(request):
    title = "How many hours did this lab member use tools in this period?"
    form = (
        PersonDateRangeToolForm(request.POST or None)
        if request.method == "POST"
        else PersonDateRangeToolForm.default_previous_month()
    )
    if request.method == "POST" and form.is_valid():
        user = form.cleaned_data["user"]
        start, end = form.cleaned_data["start"], form.cleaned_data["end"]
        tool = form.cleaned_data.get("tool")
        qs = usage_events_queryset(
            start=start,
            end=end,
            user=user,
            tool=tool,
            completed_only=True,
            end_in_range=True,
        )
        summary = completed_hours_summary(qs, group_by="tool")
        if request.POST.get("action") == "download":
            sheets = {
                "By tool": (SUMMARY_HEADERS, summary_rows(summary.breakdown)),
                "Sessions": (USAGE_HEADERS, usage_rows_from_qs(summary.sessions)),
            }
            _log(
                request,
                "person-hours",
                filter_summary_from_cleaned(form.cleaned_data),
                summary.session_count,
                LookupLog.Outcome.DOWNLOADED,
            )
            return xlsx_response(f"person_hours_{user.username}_{start}_{end}.xlsx", sheets)
        tool_part = f" on {tool.name}" if tool else ""
        answer = (
            f"{person_short(user)} used tools{tool_part} for {summary.total_hours} hours across "
            f"{summary.session_count} sessions from {start.isoformat()} to {end.isoformat()}."
        )
        tables = [
            {"title": "By tool", "headers": SUMMARY_HEADERS, "rows": summary_rows(summary.breakdown)},
            {"title": "Sessions", "headers": USAGE_HEADERS, "rows": usage_rows_from_qs(summary.sessions)},
        ]
        _log(request, "person-hours", filter_summary_from_cleaned(form.cleaned_data), summary.session_count, LookupLog.Outcome.ANSWERED, answer)
        return render(
            request,
            "NEMO_lookup/question.html",
            _question_context(title, form, answer=answer, tables=tables, download_ready=True),
        )
    return render(request, "NEMO_lookup/question.html", _question_context(title, form))


@login_required
@permission_required(PERM, raise_exception=True)
@require_http_methods(["GET", "POST"])
def question_qualified_on(request):
    title = "When was this lab member qualified on this tool?"
    form = PersonToolForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user, tool = form.cleaned_data["user"], form.cleaned_data["tool"]
        qualification = qualification_for_pair(user, tool)
        trainings = training_sessions_for_pair(user, tool)
        training_list = list(trainings)
        if request.POST.get("action") == "download":
            sheets = {"Training history": (TRAINING_HEADERS, training_rows_from_qs(training_list))}
            if qualification:
                sheets["Qualification"] = (QUALIFICATION_HEADERS, [qualification_rows_from_qs([qualification])[0]])
            _log(
                request,
                "qualified-on",
                filter_summary_from_cleaned(form.cleaned_data),
                len(training_list),
                LookupLog.Outcome.DOWNLOADED,
            )
            return xlsx_response("qualification.xlsx", sheets)
        if qualification:
            level = ""
            if qualification.qualification_level_id:
                level = f" ({qualification.qualification_level.name})"
            date_str = format_datetime(qualification.qualified_on, "F j, Y") if qualification.qualified_on else ""
            answer = f"{person_short(user)} was qualified on {tool.name} on {date_str}{level}."
        else:
            answer = f"{person_short(user)} is not qualified on {tool.name}."
        tables = [
            {
                "title": "Training history",
                "headers": TRAINING_HEADERS,
                "rows": training_rows_from_qs(training_list),
            }
        ]
        _log(
            request,
            "qualified-on",
            filter_summary_from_cleaned(form.cleaned_data),
            len(training_list),
            LookupLog.Outcome.ANSWERED,
            answer,
        )
        return render(
            request,
            "NEMO_lookup/question.html",
            _question_context(title, form, answer=answer, tables=tables, download_ready=True),
        )
    return render(request, "NEMO_lookup/question.html", _question_context(title, form or PersonToolForm()))


@login_required
@permission_required(PERM, raise_exception=True)
@require_http_methods(["GET", "POST"])
def question_lifetime_hours(request):
    title = "How many hours has this lab member used this tool?"
    form = PersonToolOptionalDatesForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user, tool = form.cleaned_data["user"], form.cleaned_data["tool"]
        start, end = form.cleaned_data.get("start"), form.cleaned_data.get("end")
        qs = usage_events_queryset(
            start=start,
            end=end,
            user=user,
            tool=tool,
            completed_only=True,
            end_in_range=bool(start and end),
        )
        # When dates are blank, do not apply a date filter (usage_events_queryset already skips when start/end None)
        summary = completed_hours_summary(qs, group_by="user")
        if request.POST.get("action") == "download":
            sheets = {"Sessions": (USAGE_HEADERS, usage_rows_from_qs(summary.sessions))}
            _log(
                request,
                "lifetime-hours",
                filter_summary_from_cleaned(form.cleaned_data),
                summary.session_count,
                LookupLog.Outcome.DOWNLOADED,
            )
            return xlsx_response(f"lifetime_hours_{user.username}_{tool.name}.xlsx", sheets)
        span = f"from {start.isoformat()} to {end.isoformat()}" if start and end else "all time"
        answer = (
            f"{person_short(user)} used {tool.name} for {summary.total_hours} hours across "
            f"{summary.session_count} sessions ({span})."
        )
        tables = [{"title": "Sessions", "headers": USAGE_HEADERS, "rows": usage_rows_from_qs(summary.sessions)}]
        _log(
            request,
            "lifetime-hours",
            filter_summary_from_cleaned(form.cleaned_data),
            summary.session_count,
            LookupLog.Outcome.ANSWERED,
            answer,
        )
        return render(
            request,
            "NEMO_lookup/question.html",
            _question_context(title, form, answer=answer, tables=tables, download_ready=True),
        )
    return render(request, "NEMO_lookup/question.html", _question_context(title, form or PersonToolOptionalDatesForm()))


@login_required
@permission_required(PERM, raise_exception=True)
@require_http_methods(["GET", "POST"])
def question_qualifications(request):
    title = "Which tools is this lab member qualified on?"
    form = PersonOnlyForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.cleaned_data["user"]
        qs = qualifications_for_user(user)
        rows = qualification_rows_from_qs(qs)
        if request.POST.get("action") == "download":
            _log(
                request,
                "qualifications",
                filter_summary_from_cleaned(form.cleaned_data),
                len(rows),
                LookupLog.Outcome.DOWNLOADED,
            )
            return xlsx_response(
                f"qualifications_{user.username}.xlsx",
                {"Qualifications": (QUALIFICATION_HEADERS, rows)},
            )
        if rows:
            answer = f"{person_short(user)} is qualified on {len(rows)} tools."
        else:
            answer = f"{person_short(user)} is not qualified on any tools."
        tables = [{"title": "Qualifications", "headers": QUALIFICATION_HEADERS, "rows": rows}]
        _log(
            request,
            "qualifications",
            filter_summary_from_cleaned(form.cleaned_data),
            len(rows),
            LookupLog.Outcome.ANSWERED,
            answer,
        )
        return render(
            request,
            "NEMO_lookup/question.html",
            _question_context(title, form, answer=answer, tables=tables, download_ready=True),
        )
    return render(request, "NEMO_lookup/question.html", _question_context(title, form or PersonOnlyForm()))


def _search_display_last_first(user: User) -> str:
    return f"{user.last_name}, {user.first_name} ({user.username})"


@login_required
@permission_required(PERM, raise_exception=True)
@require_GET
def search_users(request):
    # Custom display: "Last, First (username)" for staff-friendly suggestions.
    from django.contrib.admin.options import ModelAdmin
    from NEMO.utilities import is_ajax

    if not is_ajax(request):
        return HttpResponse("This request can only be made as an ajax call", content_type="application/json")
    query = request.GET.get("query", "")
    qs = User.objects.all()
    admin_model = ModelAdmin(User, None)
    admin_model.search_fields = ["first_name", "last_name", "username"]
    search_qs, search_use_distinct = admin_model.get_search_results(None, qs, query)
    if search_use_distinct:
        search_qs = search_qs.distinct()
    parts = []
    for user in search_qs[:50]:
        name = escapejs(_search_display_last_first(user))
        parts.append(f'{{"name":"{name}", "id":"{user.id}", "type":"user"}}')
    return HttpResponse("[" + ",".join(parts) + "]", content_type="application/json")


@login_required
@permission_required(PERM, raise_exception=True)
@require_GET
def search_tools(request):
    return queryset_search_filter(Tool.objects.filter(visible=True), ["name"], request)
