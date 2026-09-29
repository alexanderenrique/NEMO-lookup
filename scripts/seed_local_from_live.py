#!/usr/bin/env python3
"""
Pull a testing slice from live NEMO and load it into the local Postgres DB.

Usage (from nemo-ce-alex, with its venv):

  cd /Users/adenton/Desktop/NEMO/nemo-ce-alex
  ./venv/bin/python ../NEMO-lookup/scripts/seed_local_from_live.py

Reads NEMO_TOKEN from NEMO-VM/.env. Never prints the token or personal data.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence
from zoneinfo import ZoneInfo

import requests

NEMO_CE_ROOT = Path("/Users/adenton/Desktop/NEMO/nemo-ce-alex")
LOOKUP_ROOT = Path("/Users/adenton/Desktop/NEMO/NEMO-lookup")
VM_ENV = Path("/Users/adenton/Desktop/NEMO/NEMO-VM/.env")
LIVE_API = "https://nemo.stanford.edu/api"
PACIFIC = ZoneInfo("America/Los_Angeles")
PAGE_SIZE = 1000
BATCH = 500
REQUEST_TIMEOUT = 180

LOCAL_LOGIN_USERNAME = "local-lookup"


def _load_env_token() -> str:
    if not VM_ENV.exists():
        raise SystemExit(f"Missing {VM_ENV}")
    for line in VM_ENV.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip() == "NEMO_TOKEN":
            token = value.strip().strip("'").strip('"')
            if token:
                return token
    raise SystemExit("NEMO_TOKEN not found in NEMO-VM/.env")


def _setup_django() -> None:
    sys.path.insert(0, str(NEMO_CE_ROOT))
    sys.path.insert(0, str(LOOKUP_ROOT))
    plugins = NEMO_CE_ROOT / "NEMO" / "plugins"
    if plugins.is_dir():
        sys.path.insert(0, str(plugins))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "resources.settings")
    import django

    django.setup()


CACHE_DIR = LOOKUP_ROOT / "scripts" / ".seed_cache"


def dedupe_by_id(rows: List[Dict[str, Any]], label: str) -> List[Dict[str, Any]]:
    seen = set()
    unique: List[Dict[str, Any]] = []
    for row in rows:
        row_id = row.get("id")
        if row_id in seen:
            continue
        seen.add(row_id)
        unique.append(row)
    dropped = len(rows) - len(unique)
    if dropped:
        print(f"  {label}: dropped {dropped} duplicate id(s) from pagination overlap")
    return unique


def fetch_all(
    session: requests.Session,
    path: str,
    params: Optional[Dict[str, Any]] = None,
    *,
    cache_key: Optional[str] = None,
) -> List[Dict[str, Any]]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{cache_key or path.strip('/').replace('/', '_')}.json"
    if cache_file.exists():
        import json

        data = dedupe_by_id(json.loads(cache_file.read_text()), path)
        print(f"  {path}: {len(data)} rows (from cache {cache_file.name})")
        return data

    params = dict(params or {})
    params.setdefault("page_size", PAGE_SIZE)
    url = f"{LIVE_API}/{path.lstrip('/')}"
    results: List[Dict[str, Any]] = []
    page = 1
    while url:
        response = session.get(url, params=params, timeout=REQUEST_TIMEOUT)
        if response.status_code != 200:
            raise SystemExit(f"GET {path} failed: HTTP {response.status_code}: {response.text[:300]}")
        data = response.json()
        if isinstance(data, list):
            results.extend(data)
            print(f"  {path}: {len(results)} rows (non-paginated)")
            break
        batch = data.get("results") or []
        results.extend(batch)
        total = data.get("count", "?")
        print(f"  {path}: page {page}, +{len(batch)} (running {len(results)} / {total})")
        url = data.get("next")
        params = None  # next URL already includes query string
        page += 1

    import json

    results = dedupe_by_id(results, path)
    cache_file.write_text(json.dumps(results))
    return results


def parse_dt(value: Any) -> Optional[datetime]:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).replace("Z", "+00:00")
    return datetime.fromisoformat(text)


def parse_date(value: Any):
    if value in (None, ""):
        return None
    if hasattr(value, "year") and not isinstance(value, datetime):
        return value
    dt = parse_dt(value)
    return dt.date() if dt else None


def chunks(items: Sequence[Any], size: int = BATCH) -> Iterable[Sequence[Any]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def model_concrete_names(model) -> set[str]:
    return {f.name for f in model._meta.concrete_fields}


def pick_fields(model, row: Dict[str, Any], *, skip: Optional[set[str]] = None, null_fks: Optional[set[str]] = None) -> Dict[str, Any]:
    skip = skip or set()
    null_fks = null_fks or set()
    allowed = model_concrete_names(model)
    out: Dict[str, Any] = {}
    for key, value in row.items():
        if key in skip or key not in allowed:
            continue
        field = model._meta.get_field(key)
        # Foreign keys from the API are integer PKs — assign via attname (foo_id).
        if getattr(field, "is_relation", False) and getattr(field, "many_to_one", False):
            att = field.attname  # e.g. type_id
            if key in null_fks:
                out[att] = None
            else:
                out[att] = value
            continue
        if key in null_fks:
            out[key] = None
            continue
        internal = getattr(field, "get_internal_type", lambda: "")()
        if internal in ("DateTimeField",):
            out[key] = parse_dt(value)
        elif internal in ("DateField",):
            out[key] = parse_date(value)
        elif internal in ("TimeField",) and value not in (None, ""):
            out[key] = value
        elif key == "badge_number" and value == "":
            out[key] = None
        else:
            out[key] = value
    return out


def bulk_insert(model, objects: List[Any], label: str) -> int:
    if not objects:
        print(f"  skip {label}: 0")
        return 0
    created = 0
    for batch in chunks(objects):
        model.objects.bulk_create(batch, batch_size=BATCH)
        created += len(batch)
    print(f"  loaded {label}: {created}")
    return created


def reset_sequences(models: List[Any]) -> None:
    from django.db import connection

    with connection.cursor() as cursor:
        for model in models:
            table = model._meta.db_table
            pk = model._meta.pk.column
            cursor.execute(
                f"""
                SELECT setval(
                    pg_get_serial_sequence('"{table}"', '{pk}'),
                    COALESCE((SELECT MAX("{pk}") FROM "{table}"), 1),
                    true
                )
                """
            )


def report_counts() -> Dict[str, int]:
    from NEMO.models import Account, Project, Qualification, Reservation, Tool, TrainingSession, UsageEvent, User
    from NEMO_lookup.exports import reservations_queryset, usage_events_queryset, users_queryset
    from django.utils import timezone

    today = timezone.localdate()
    start = today - timedelta(days=62)
    counts = {
        "users": User.objects.count(),
        "tools": Tool.objects.count(),
        "accounts": Account.objects.count(),
        "projects": Project.objects.count(),
        "qualifications": Qualification.objects.count(),
        "usage_events_all": UsageEvent.objects.count(),
        "reservations_all": Reservation.objects.count(),
        "training_sessions": TrainingSession.objects.count(),
        "users_queryset": users_queryset().count(),
        "usage_events_window": usage_events_queryset(start=start, end=today).count(),
        "reservations_window": reservations_queryset(start=start, end=today).count(),
    }
    return counts


def print_counts(counts: Dict[str, int], title: str) -> None:
    print(title)
    for key, value in counts.items():
        print(f"  {key}: {value}")


def is_bootstrap_only() -> bool:
    from NEMO.models import Reservation, Tool, UsageEvent, User

    return (
        User.objects.count() <= 2
        and Tool.objects.count() == 0
        and UsageEvent.objects.count() == 0
        and Reservation.objects.count() == 0
    )


def clear_bootstrap_users() -> None:
    from django.db import connection
    from NEMO.models import User

    n = User.objects.count()
    # Avoid CASCADE into optional billing tables that may not be migrated locally.
    with connection.cursor() as cursor:
        for table in (
            "authtoken_token",
            "NEMO_user_groups",
            "NEMO_user_user_permissions",
            "NEMO_user_projects",
            "NEMO_user_managed_projects",
            "NEMO_user_managed_accounts",
            "NEMO_user_managed_users",
            "NEMO_user_onboarding_phases",
            "NEMO_user_physical_access_levels",
            "NEMO_user_safety_trainings",
            "NEMO_userpreferences_tool_freed_time_notifications",
            "NEMO_userpreferences_tool_task_notifications",
            "NEMO_usercalendartoollist_tools",
            "NEMO_usercalendartoollist",
            "NEMO_userdocuments",
            "NEMO_userpreferences",
            "django_admin_log",
            "NEMO_user",
        ):
            cursor.execute("SELECT to_regclass(%s)", [f"public.{table}"])
            if cursor.fetchone()[0]:
                cursor.execute(f'DELETE FROM "{table}"')
    remaining = User.objects.count()
    if remaining:
        raise SystemExit(f"Failed to clear bootstrap users; still have {remaining}")
    print(f"Cleared {n} bootstrap user(s) before seed")


def ensure_user_types(type_ids: Iterable[int]) -> None:
    from NEMO.models import UserType

    for type_id in sorted({i for i in type_ids if i is not None}):
        UserType.objects.update_or_create(
            id=type_id,
            defaults={"name": f"Type {type_id}", "display_order": type_id},
        )


def create_local_login() -> str:
    """Create a local superuser for DEBUG LocalDevBackend (password ignored)."""
    from django.contrib.auth.models import Permission
    from NEMO.models import User

    user, created = User.objects.get_or_create(
        username=LOCAL_LOGIN_USERNAME,
        defaults={
            "first_name": "Local",
            "last_name": "Lookup",
            "email": "local-lookup@example.com",
            "is_active": True,
            "is_staff": True,
            "is_superuser": True,
            "training_required": False,
        },
    )
    user.is_staff = True
    user.is_superuser = True
    user.is_active = True
    user.training_required = False
    # NEMO User has no password field; LocalDevBackend accepts any active username.
    user.save()
    try:
        perm = Permission.objects.get(codename="use_lookup", content_type__app_label="lookup")
        user.user_permissions.add(perm)
    except Permission.DoesNotExist:
        print("  note: lookup.use_lookup permission not found yet (migrate lookup if needed)")
    action = "Created" if created else "Updated"
    print(f"{action} local login user {LOCAL_LOGIN_USERNAME}")
    return "(any — LocalDevBackend ignores password when DEBUG=True)"


def window_bounds() -> tuple[datetime, datetime]:
    now = datetime.now(PACIFIC)
    start = (now - timedelta(days=62)).replace(hour=0, minute=0, second=0, microsecond=0)
    end = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return start, end


def main() -> None:
    token = _load_env_token()
    _setup_django()

    from django.db import transaction
    from NEMO.models import (
        Account,
        AccountType,
        Project,
        Qualification,
        Reservation,
        Tool,
        TrainingSession,
        TrainingTechnique,
        UsageEvent,
        User,
        UserType,
    )

    existing = report_counts()
    if existing["users"] > 0 and not is_bootstrap_only():
        print_counts(existing, "Local DB already has data; refusing to overwrite. Current counts:")
        raise SystemExit(1)
    if existing["users"] > 0 and is_bootstrap_only():
        clear_bootstrap_users()

    start, end = window_bounds()
    start_s = start.isoformat()
    end_s = end.isoformat()
    print(f"Event window: {start_s} .. {end_s} (Pacific)")

    session = requests.Session()
    session.headers.update({"Authorization": f"Token {token}", "Accept": "application/json"})

    print("Fetching reference data from live…")
    account_types = fetch_all(session, "account_types/", cache_key="account_types")
    accounts = fetch_all(session, "accounts/", cache_key="accounts")
    projects = fetch_all(session, "projects/", cache_key="projects")
    users = fetch_all(session, "users/", cache_key="users")
    tools = fetch_all(session, "tools/", cache_key="tools")
    techniques = fetch_all(session, "training_techniques/", cache_key="training_techniques")
    qualifications = fetch_all(session, "qualifications/", cache_key="qualifications")

    print("Fetching timed data from live…")
    usage_events = fetch_all(
        session,
        "usage_events/",
        {"start__gte": start_s, "start__lt": end_s},
        cache_key=f"usage_events_{start.date()}_{end.date()}",
    )
    reservations = fetch_all(
        session,
        "reservations/",
        {"start__gte": start_s, "start__lt": end_s},
        cache_key=f"reservations_{start.date()}_{end.date()}",
    )
    training_sessions = fetch_all(
        session,
        "training_sessions/",
        {"date__gte": start_s, "date__lt": end_s},
        cache_key=f"training_sessions_{start.date()}_{end.date()}",
    )

    print("Writing to local database…")
    with transaction.atomic():
        ensure_user_types(u.get("type") for u in users)

        bulk_insert(
            AccountType,
            [
                AccountType(**pick_fields(AccountType, row))
                for row in account_types
            ],
            "account_types",
        )

        bulk_insert(
            Account,
            [Account(**pick_fields(Account, row)) for row in accounts],
            "accounts",
        )

        project_objs = []
        for row in projects:
            fields = pick_fields(
                Project,
                row,
                skip={"only_allow_tools", "project_types", "principal_investigators", "users"},
                null_fks={"discipline"},
            )
            project_objs.append(Project(**fields))
        bulk_insert(Project, project_objs, "projects")

        user_project_links: List[tuple[int, List[int]]] = []
        user_managed_links: List[tuple[int, List[int]]] = []
        user_objs = []
        for row in users:
            fields = pick_fields(
                User,
                row,
                skip={
                    "groups",
                    "user_permissions",
                    "onboarding_phases",
                    "safety_trainings",
                    "physical_access_levels",
                    "qualifications",
                    "projects",
                    "managed_projects",
                    "managed_accounts",
                    "managed_users",
                    "user_documents",
                    "preferences",
                    "gender_name",
                    "race_name",
                    "ethnicity_name",
                    "education_level_name",
                },
            )
            user = User(**fields)
            user.set_unusable_password()
            user_objs.append(user)
            user_project_links.append((row["id"], row.get("projects") or []))
            user_managed_links.append((row["id"], row.get("managed_projects") or []))
        bulk_insert(User, user_objs, "users")

        # First pass: tools without parent / owner FKs that may not exist yet
        tool_null_fks = {
            "parent_tool",
            "_interlock",
            "_requires_area_access",
            "_grant_physical_access_level_upon_qualification",
        }
        tool_skip = {
            "_image",
            "_backup_owners",
            "_superusers",
            "_staff",
            "_adjustment_request_reviewers",
            "_grant_access_for_qualification_levels",
            "_shadowing_verification_request_qualification_levels",
            "_shadowing_verification_reviewers",
        }
        owner_ids = set(User.objects.values_list("id", flat=True))
        tool_parent: Dict[int, Optional[int]] = {}
        tool_objs = []
        for row in tools:
            tool_parent[row["id"]] = row.get("parent_tool")
            fields = pick_fields(Tool, row, skip=tool_skip, null_fks=tool_null_fks)
            owner = row.get("_primary_owner")
            if owner and owner not in owner_ids:
                fields["_primary_owner_id"] = None
            tool_objs.append(Tool(**fields))
        bulk_insert(Tool, tool_objs, "tools")

        parent_updates = []
        for tool_id, parent_id in tool_parent.items():
            if parent_id:
                parent_updates.append(Tool(id=tool_id, parent_tool_id=parent_id))
        if parent_updates:
            Tool.objects.bulk_update(parent_updates, ["parent_tool"], batch_size=BATCH)
            print(f"  linked tool parents: {len(parent_updates)}")

        bulk_insert(
            TrainingTechnique,
            [TrainingTechnique(**pick_fields(TrainingTechnique, row)) for row in techniques],
            "training_techniques",
        )

        known_user_ids = {u.id for u in user_objs}
        known_tool_ids = {t["id"] for t in tools}
        known_project_ids = {p["id"] for p in projects}

        qual_objs = []
        skipped_qual = 0
        for row in qualifications:
            if row.get("user") not in known_user_ids or row.get("tool") not in known_tool_ids:
                skipped_qual += 1
                continue
            qual_objs.append(
                Qualification(**pick_fields(Qualification, row, null_fks={"qualification_level"}))
            )
        bulk_insert(Qualification, qual_objs, "qualifications")
        if skipped_qual:
            print(f"  skipped qualifications (missing user/tool): {skipped_qual}")

        usage_objs = []
        skipped_usage = 0
        for row in usage_events:
            fields = pick_fields(UsageEvent, row, null_fks={"staff_charge", "validated_by", "waived_by"})
            if (
                fields.get("user_id") not in known_user_ids
                or fields.get("operator_id") not in known_user_ids
                or fields.get("tool_id") not in known_tool_ids
                or fields.get("project_id") not in known_project_ids
            ):
                skipped_usage += 1
                continue
            # validated_by / waived_by may point at missing users
            if fields.get("validated_by_id") not in known_user_ids:
                fields["validated_by_id"] = None
            if fields.get("waived_by_id") not in known_user_ids:
                fields["waived_by_id"] = None
            usage_objs.append(UsageEvent(**fields))
        bulk_insert(UsageEvent, usage_objs, "usage_events")
        if skipped_usage:
            print(f"  skipped usage_events (missing FK): {skipped_usage}")

        reservation_descendant: Dict[int, Optional[int]] = {}
        reservation_objs = []
        skipped_res = 0
        for row in reservations:
            fields = pick_fields(
                Reservation,
                row,
                skip={"configuration_options", "tool_accessories", "invitee"},
                null_fks={"descendant", "area", "validated_by", "waived_by"},
            )
            if fields.get("user_id") not in known_user_ids or fields.get("creator_id") not in known_user_ids:
                skipped_res += 1
                continue
            if fields.get("tool_id") is None and fields.get("area_id") is None:
                # tool-less after nulling area — skip
                if row.get("tool") not in known_tool_ids and not row.get("area"):
                    skipped_res += 1
                    continue
            if fields.get("tool_id") is not None and fields.get("tool_id") not in known_tool_ids:
                skipped_res += 1
                continue
            if fields.get("project_id") is not None and fields.get("project_id") not in known_project_ids:
                fields["project_id"] = None
            if fields.get("cancelled_by_id") not in known_user_ids:
                fields["cancelled_by_id"] = None
            reservation_descendant[row["id"]] = row.get("descendant")
            reservation_objs.append(Reservation(**fields))
        bulk_insert(Reservation, reservation_objs, "reservations")
        if skipped_res:
            print(f"  skipped reservations (missing FK): {skipped_res}")

        desc_updates = []
        known_reservation_ids = {r.id for r in reservation_objs}
        for res_id, desc_id in reservation_descendant.items():
            if desc_id and desc_id in known_reservation_ids:
                desc_updates.append(Reservation(id=res_id, descendant_id=desc_id))
        if desc_updates:
            Reservation.objects.bulk_update(desc_updates, ["descendant"], batch_size=BATCH)
            print(f"  linked reservation descendants: {len(desc_updates)}")

        # Training sessions may reference usage events / qualifications outside the window — null those
        known_usage = {u.id for u in usage_objs}
        known_qual = {q.id for q in qual_objs}
        known_tech = set(TrainingTechnique.objects.values_list("id", flat=True))
        training_objs = []
        skipped_train = 0
        for row in training_sessions:
            fields = pick_fields(
                TrainingSession,
                row,
                null_fks={"validated_by", "waived_by"},
            )
            if (
                fields.get("trainer_id") not in known_user_ids
                or fields.get("trainee_id") not in known_user_ids
                or fields.get("tool_id") not in known_tool_ids
                or fields.get("project_id") not in known_project_ids
            ):
                skipped_train += 1
                continue
            ue = fields.get("usage_event_id")
            if ue is not None and ue not in known_usage:
                fields["usage_event_id"] = None
            qual = fields.get("qualification_id")
            if qual is not None and qual not in known_qual:
                fields["qualification_id"] = None
            tech = fields.get("technique_id")
            if tech is not None and tech not in known_tech:
                fields["technique_id"] = None
            training_objs.append(TrainingSession(**fields))
        bulk_insert(TrainingSession, training_objs, "training_sessions")
        if skipped_train:
            print(f"  skipped training_sessions (missing FK): {skipped_train}")

        # M2M: user projects / managed projects
        project_ids = known_project_ids
        ThroughProjects = User.projects.through
        ThroughManaged = User.managed_projects.through
        project_links = []
        managed_links = []
        for user_id, pids in user_project_links:
            if user_id not in known_user_ids:
                continue
            for pid in pids:
                if pid in project_ids:
                    project_links.append(ThroughProjects(user_id=user_id, project_id=pid))
        for user_id, pids in user_managed_links:
            if user_id not in known_user_ids:
                continue
            for pid in pids:
                if pid in project_ids:
                    managed_links.append(ThroughManaged(user_id=user_id, project_id=pid))
        if project_links:
            ThroughProjects.objects.bulk_create(project_links, batch_size=BATCH, ignore_conflicts=True)
            print(f"  user→project links: {len(project_links)}")
        if managed_links:
            ThroughManaged.objects.bulk_create(managed_links, batch_size=BATCH, ignore_conflicts=True)
            print(f"  user→managed_project links: {len(managed_links)}")

        reset_sequences(
            [
                AccountType,
                Account,
                Project,
                UserType,
                User,
                Tool,
                TrainingTechnique,
                Qualification,
                UsageEvent,
                Reservation,
                TrainingSession,
            ]
        )

    password = create_local_login()
    final = report_counts()
    print_counts(final, "Seed complete. Counts:")
    print(f"Local UI login: username={LOCAL_LOGIN_USERNAME} password={password}")


if __name__ == "__main__":
    main()
