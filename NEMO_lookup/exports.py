"""ORM queries and Excel builders for lookup exports and questions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from io import BytesIO
from typing import Iterable, List, Optional, Sequence

from django.db.models import Q, QuerySet
from django.http import HttpResponse
from django.utils import timezone
from openpyxl import Workbook

from NEMO.models import Project, Qualification, Reservation, Tool, TrainingSession, UsageEvent, User, UserType
from NEMO.utilities import format_datetime

ROW_CAP = 50_000


def previous_month_range(today: Optional[date] = None) -> tuple[date, date]:
    today = today or timezone.localdate()
    last_of_prev = today.replace(day=1) - timedelta(days=1)
    return last_of_prev.replace(day=1), last_of_prev


def day_start(d: date) -> datetime:
    return timezone.make_aware(datetime.combine(d, time.min))


def day_end(d: date) -> datetime:
    return timezone.make_aware(datetime.combine(d, time.max))


def person_display(user: Optional[User]) -> str:
    if not user:
        return ""
    return f"{user.last_name}, {user.first_name} ({user.username})"


def person_short(user: Optional[User]) -> str:
    if not user:
        return ""
    return user.get_name()


def format_local(dt: Optional[datetime]) -> str:
    if not dt:
        return ""
    return format_datetime(dt, "Y-m-d H:i:s")


def hours_between(start: Optional[datetime], end: Optional[datetime]) -> Optional[Decimal]:
    if not start or not end:
        return None
    seconds = (end - start).total_seconds()
    if seconds < 0:
        return None
    return round(Decimal(seconds) / Decimal(3600), 2)


def yes_no(value: bool) -> str:
    return "Yes" if value else "No"


def user_type_name(user: Optional[User]) -> str:
    if not user or not user.type_id:
        return ""
    return str(user.type)


# --- Querysets -----------------------------------------------------------------


def usage_events_queryset(
    *,
    start: Optional[date] = None,
    end: Optional[date] = None,
    user_type: Optional[UserType] = None,
    tool: Optional[Tool] = None,
    project: Optional[Project] = None,
    user: Optional[User] = None,
    completed_only: bool = False,
    end_in_range: bool = False,
) -> QuerySet:
    qs = UsageEvent.objects.select_related(
        "user",
        "user__type",
        "operator",
        "project",
        "project__account",
        "tool",
    )
    if start is not None and end is not None:
        start_dt, end_dt = day_start(start), day_end(end)
        if end_in_range:
            qs = qs.filter(end__gte=start_dt, end__lte=end_dt)
        else:
            # Overlap: started before window end, and either still open or ended after window start
            qs = qs.filter(start__lte=end_dt).filter(Q(end__isnull=True) | Q(end__gte=start_dt))
    if completed_only:
        qs = qs.filter(end__isnull=False)
    if user_type is not None:
        qs = qs.filter(user__type=user_type)
    if tool is not None:
        qs = qs.filter(tool=tool)
    if project is not None:
        qs = qs.filter(project=project)
    if user is not None:
        qs = qs.filter(user=user)
    return qs.order_by("-start")


def reservations_queryset(
    *,
    start: date,
    end: date,
    status: str = "all",
    user_type: Optional[UserType] = None,
    tool: Optional[Tool] = None,
    project: Optional[Project] = None,
) -> QuerySet:
    start_dt, end_dt = day_start(start), day_end(end)
    qs = Reservation.objects.select_related(
        "user",
        "user__type",
        "creator",
        "cancelled_by",
        "project",
        "project__account",
        "tool",
        "area",
    ).filter(start__lte=end_dt, end__gte=start_dt)
    if status == "not_cancelled":
        qs = qs.filter(cancelled=False)
    elif status == "cancelled":
        qs = qs.filter(cancelled=True)
    elif status == "missed":
        qs = qs.filter(missed=True)
    if user_type is not None:
        qs = qs.filter(user__type=user_type)
    if tool is not None:
        qs = qs.filter(tool=tool)
    if project is not None:
        qs = qs.filter(project=project)
    return qs.order_by("-start")


def users_queryset(
    *,
    user_type: Optional[UserType] = None,
    account: str = "all",
    role: str = "all",
    access: str = "any",
) -> QuerySet:
    qs = User.objects.select_related("type").prefetch_related("projects", "managed_projects")
    if user_type is not None:
        qs = qs.filter(type=user_type)
    if account == "active":
        qs = qs.filter(is_active=True)
    elif account == "inactive":
        qs = qs.filter(is_active=False)
    role_map = {
        "staff": "is_staff",
        "user_office": "is_user_office",
        "facility_manager": "is_facility_manager",
        "accounting_officer": "is_accounting_officer",
        "service_personnel": "is_service_personnel",
    }
    if role in role_map:
        qs = qs.filter(**{role_map[role]: True})
    today = timezone.localdate()
    if access == "expired":
        qs = qs.filter(access_expiration__lt=today)
    elif access == "not_expired":
        qs = qs.filter(Q(access_expiration__isnull=True) | Q(access_expiration__gte=today))
    return qs.order_by("last_name", "first_name")


def qualifications_for_user(user: User) -> QuerySet:
    return (
        Qualification.objects.filter(user=user)
        .select_related("tool", "qualification_level")
        .order_by("tool__name")
    )


def qualification_for_pair(user: User, tool: Tool) -> Optional[Qualification]:
    return (
        Qualification.objects.filter(user=user, tool=tool)
        .select_related("tool", "qualification_level")
        .first()
    )


def training_sessions_for_pair(user: User, tool: Tool) -> QuerySet:
    return (
        TrainingSession.objects.filter(trainee=user, tool=tool)
        .select_related("trainer", "tool", "technique")
        .order_by("-date")
    )


# --- Row builders --------------------------------------------------------------


USAGE_HEADERS = [
    "Tool",
    "User",
    "Username",
    "User type",
    "Operator",
    "Operator username",
    "Project",
    "Account",
    "Start",
    "End",
    "Hours",
    "Note",
    "Training",
    "Remote work",
    "Validated",
    "Waived",
]

RESERVATION_HEADERS = [
    "Tool or area",
    "Item type",
    "User",
    "Username",
    "User type",
    "Creator",
    "Project",
    "Account",
    "Start",
    "End",
    "Hours",
    "Cancelled",
    "Missed",
    "Shortened",
    "Cancellation time",
    "Cancelled by",
    "Short notice",
    "Title",
    "Note",
]

USER_HEADERS = [
    "Username",
    "First name",
    "Last name",
    "Email",
    "User type",
    "Active",
    "Staff",
    "User office",
    "Accounting officer",
    "Facility manager",
    "Service personnel",
    "Technician",
    "Date joined",
    "Last login",
    "Access expiration",
    "Projects",
    "Managed projects (PI)",
]

QUALIFICATION_HEADERS = ["Tool", "Level", "Qualified on"]

TRAINING_HEADERS = ["Tool", "Trainee", "Trainer", "Date", "Type", "Technique", "Qualified", "Comment"]

SUMMARY_HEADERS = ["Name", "Sessions", "Hours"]


def usage_event_row(event: UsageEvent) -> list:
    hours = hours_between(event.start, event.end)
    return [
        event.tool.name if event.tool_id else "",
        person_short(event.user),
        event.user.username if event.user_id else "",
        user_type_name(event.user),
        person_short(event.operator),
        event.operator.username if event.operator_id else "",
        event.project.name if event.project_id else "",
        event.project.account.name if event.project_id and event.project.account_id else "",
        format_local(event.start),
        format_local(event.end),
        float(hours) if hours is not None else "",
        event.note or "",
        yes_no(event.training),
        yes_no(event.remote_work),
        yes_no(event.validated),
        yes_no(event.waived),
    ]


def reservation_row(reservation: Reservation) -> list:
    item = reservation.reservation_item
    item_type = ""
    if reservation.tool_id:
        item_type = "tool"
    elif reservation.area_id:
        item_type = "area"
    hours = hours_between(reservation.start, reservation.end)
    return [
        item.name if item else "",
        item_type,
        person_short(reservation.user),
        reservation.user.username if reservation.user_id else "",
        user_type_name(reservation.user),
        person_short(reservation.creator),
        reservation.project.name if reservation.project_id else "",
        reservation.project.account.name if reservation.project_id and reservation.project.account_id else "",
        format_local(reservation.start),
        format_local(reservation.end),
        float(hours) if hours is not None else "",
        yes_no(reservation.cancelled),
        yes_no(reservation.missed),
        yes_no(reservation.shortened),
        format_local(reservation.cancellation_time),
        person_short(reservation.cancelled_by),
        yes_no(reservation.short_notice) if reservation.short_notice is not None else "",
        reservation.title or "",
        reservation.note or "",
    ]


def user_row(user: User) -> list:
    projects = ", ".join(p.name for p in user.projects.all())
    managed = ", ".join(p.name for p in user.managed_projects.all())
    return [
        user.username,
        user.first_name,
        user.last_name,
        user.email,
        user_type_name(user),
        yes_no(user.is_active),
        yes_no(user.is_staff),
        yes_no(user.is_user_office),
        yes_no(user.is_accounting_officer),
        yes_no(user.is_facility_manager),
        yes_no(user.is_service_personnel),
        yes_no(user.is_technician),
        format_local(user.date_joined),
        format_local(user.last_login),
        user.access_expiration.isoformat() if user.access_expiration else "",
        projects,
        managed,
    ]


def qualification_row(qualification: Qualification) -> list:
    level = ""
    if qualification.qualification_level_id:
        level = qualification.qualification_level.name
    return [
        qualification.tool.name if qualification.tool_id else "",
        level,
        qualification.qualified_on.isoformat() if qualification.qualified_on else "",
    ]


def training_row(session: TrainingSession) -> list:
    return [
        session.tool.name if session.tool_id else "",
        person_short(session.trainee),
        person_short(session.trainer),
        format_local(session.date),
        session.get_type_display(),
        str(session.technique) if session.technique_id else "",
        yes_no(session.qualified),
        session.comment or "",
    ]


# --- Aggregations for questions ------------------------------------------------


@dataclass
class HoursSummary:
    total_hours: Decimal
    session_count: int
    sessions: List[UsageEvent]
    breakdown: List[tuple]  # (name, sessions, hours)
    open_event: Optional[UsageEvent] = None


def completed_hours_summary(
    qs: QuerySet,
    *,
    group_by: str = "user",
) -> HoursSummary:
    sessions = list(qs.filter(end__isnull=False))
    total = Decimal("0")
    groups: dict = {}
    for event in sessions:
        hours = hours_between(event.start, event.end) or Decimal("0")
        total += hours
        if group_by == "user":
            key = person_short(event.user)
        else:
            key = event.tool.name if event.tool_id else ""
        count, hours_sum = groups.get(key, (0, Decimal("0")))
        groups[key] = (count + 1, hours_sum + hours)
    breakdown = sorted(
        [(name, count, float(hours_sum)) for name, (count, hours_sum) in groups.items()],
        key=lambda row: (-row[2], row[0].lower()),
    )
    return HoursSummary(
        total_hours=round(total, 2),
        session_count=len(sessions),
        sessions=sessions,
        breakdown=breakdown,
    )


def open_usage_for_tool(tool: Tool) -> Optional[UsageEvent]:
    return (
        UsageEvent.objects.filter(tool=tool, end__isnull=True)
        .select_related("user", "project", "tool")
        .order_by("-start")
        .first()
    )


def latest_usage(user: User, tool: Tool) -> Optional[UsageEvent]:
    return (
        UsageEvent.objects.filter(user=user, tool=tool)
        .select_related("user", "project", "tool", "operator")
        .order_by("-start")
        .first()
    )


# --- Excel --------------------------------------------------------------------


def build_xlsx(sheets: dict[str, tuple[Sequence[str], Iterable[Sequence]]]) -> bytes:
    """sheets: name -> (headers, rows)"""
    wb = Workbook(write_only=True)
    for sheet_name, (headers, rows) in sheets.items():
        ws = wb.create_sheet(title=sheet_name[:31] or "Sheet")
        ws.append(list(headers))
        for row in rows:
            ws.append(list(row))
    if not wb.sheetnames:
        wb.create_sheet("Sheet")
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def xlsx_response(filename: str, sheets: dict) -> HttpResponse:
    content = build_xlsx(sheets)
    response = HttpResponse(
        content,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def usage_rows_from_qs(qs: QuerySet) -> List[list]:
    return [usage_event_row(event) for event in qs]


def reservation_rows_from_qs(qs: QuerySet) -> List[list]:
    return [reservation_row(reservation) for reservation in qs]


def user_rows_from_qs(qs: QuerySet) -> List[list]:
    return [user_row(user) for user in qs]


def qualification_rows_from_qs(qs: QuerySet) -> List[list]:
    return [qualification_row(q) for q in qs]


def training_rows_from_qs(qs: QuerySet) -> List[list]:
    return [training_row(s) for s in qs]


def summary_rows(breakdown: List[tuple]) -> List[list]:
    return [[name, sessions, hours] for name, sessions, hours in breakdown]
