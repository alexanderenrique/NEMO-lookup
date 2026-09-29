from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.test import Client, TestCase
from django.urls import reverse
from django.utils.timezone import make_aware

from NEMO.models import Account, Project, Qualification, QualificationLevel, Reservation, Tool, UsageEvent, User, UserType
from NEMO.tests.test_utilities import login_as

from NEMO_lookup.exports import (
    hours_between,
    previous_month_range,
    usage_event_row,
    usage_events_queryset,
)
from NEMO_lookup.models import LookupLog


def _perm(codename="use_lookup", app_label="lookup"):
    return Permission.objects.get(content_type__app_label=app_label, codename=codename)


class LookupFixtureMixin:
    def setUp(self):
        self.client = Client()
        self.account = Account.objects.create(name="Acct A")
        self.project = Project.objects.create(
            name="Project Alpha", application_identifier="1-AAA-111", account=self.account
        )
        self.user_type = UserType.objects.create(name="Graduate", display_order=1)
        self.alice = User.objects.create(
            username="alice",
            first_name="Alice",
            last_name="Example",
            email="alice@example.com",
            type=self.user_type,
        )
        self.bob = User.objects.create(
            username="bob",
            first_name="Bob",
            last_name="Builder",
            email="bob@example.com",
        )
        self.alice.projects.add(self.project)
        self.bob.projects.add(self.project)
        self.tool = Tool.objects.create(name="AIX200", visible=True)
        self.tool2 = Tool.objects.create(name="SEM", visible=True)
        self.staff = User.objects.create(
            username="staffer",
            first_name="Staff",
            last_name="Member",
            email="staff@example.com",
            is_staff=True,
        )
        self.staff.user_permissions.add(_perm())
        login_as(self.client, self.staff)

        self.start = make_aware(datetime(2026, 7, 10, 9, 0, 0))
        self.end = make_aware(datetime(2026, 7, 10, 11, 0, 0))
        self.usage = UsageEvent.objects.create(
            user=self.alice,
            operator=self.alice,
            project=self.project,
            tool=self.tool,
            start=self.start,
            end=self.end,
        )


class PermissionTests(LookupFixtureMixin, TestCase):
    def test_denied_without_permission(self):
        login_as(self.client, self.alice)
        response = self.client.get(reverse("lookup"))
        self.assertEqual(response.status_code, 403)

    def test_picker_ok_with_permission(self):
        response = self.client.get(reverse("lookup"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Usage events")
        self.assertContains(response, "Which tools is this lab member qualified on?")


class ExportFilterTests(LookupFixtureMixin, TestCase):
    def test_usage_events_download(self):
        response = self.client.post(
            reverse("lookup_usage_events"),
            {"start": "2026-07-01", "end": "2026-07-31"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            response["Content-Type"],
        )
        self.assertTrue(LookupLog.objects.filter(category="usage-events", outcome="downloaded").exists())

    def test_usage_events_filter_by_user_type(self):
        UsageEvent.objects.create(
            user=self.bob,
            operator=self.bob,
            project=self.project,
            tool=self.tool,
            start=self.start + timedelta(days=1),
            end=self.end + timedelta(days=1),
        )
        qs = usage_events_queryset(
            start=date(2026, 7, 1),
            end=date(2026, 7, 31),
            user_type=self.user_type,
        )
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first().user_id, self.alice.id)

    def test_reservations_status_filter(self):
        Reservation.objects.create(
            user=self.alice,
            creator=self.alice,
            tool=self.tool,
            project=self.project,
            start=self.start,
            end=self.end,
            short_notice=False,
            cancelled=False,
            missed=True,
        )
        Reservation.objects.create(
            user=self.bob,
            creator=self.bob,
            tool=self.tool,
            project=self.project,
            start=self.start + timedelta(hours=3),
            end=self.end + timedelta(hours=3),
            short_notice=False,
            cancelled=True,
            missed=False,
        )
        response = self.client.post(
            reverse("lookup_reservations"),
            {"start": "2026-07-01", "end": "2026-07-31", "status": "missed"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(LookupLog.objects.filter(category="reservations", row_count=1).exists())

    def test_users_download(self):
        response = self.client.post(reverse("lookup_users"), {"account": "active", "role": "all", "access": "any"})
        self.assertEqual(response.status_code, 200)
        log = LookupLog.objects.filter(category="users").latest("created")
        self.assertGreaterEqual(log.row_count, 3)

    def test_row_cap(self):
        with patch("NEMO_lookup.views.ROW_CAP", 0):
            response = self.client.post(
                reverse("lookup_usage_events"),
                {"start": "2026-07-01", "end": "2026-07-31"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Narrow the filters")
        self.assertTrue(LookupLog.objects.filter(category="usage-events", outcome="failed").exists())


class HoursAndTimezoneTests(LookupFixtureMixin, TestCase):
    def test_hours_between(self):
        hours = hours_between(self.start, self.end)
        self.assertEqual(hours, Decimal("2.00"))

    def test_usage_row_pacific_strings(self):
        row = usage_event_row(self.usage)
        # America/Los_Angeles; July is PDT (UTC-7) so 09:00 local stays 09:00 if already aware local
        self.assertEqual(row[0], "AIX200")
        self.assertEqual(row[2], "alice")
        self.assertIn("2026-07-10", row[8])
        self.assertEqual(row[10], 2.0)

    def test_previous_month_range(self):
        start, end = previous_month_range(date(2026, 8, 15))
        self.assertEqual(start, date(2026, 7, 1))
        self.assertEqual(end, date(2026, 7, 31))


class QuestionTests(LookupFixtureMixin, TestCase):
    def test_last_use_ended(self):
        response = self.client.post(
            reverse("lookup_question_last_use"),
            {"user": self.alice.pk, "tool": self.tool.pk, "action": "answer"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "last used AIX200")
        self.assertContains(response, "2.00 hours")

    def test_last_use_in_progress(self):
        UsageEvent.objects.create(
            user=self.alice,
            operator=self.alice,
            project=self.project,
            tool=self.tool,
            start=make_aware(datetime(2026, 8, 1, 10, 0, 0)),
            end=None,
        )
        response = self.client.post(
            reverse("lookup_question_last_use"),
            {"user": self.alice.pk, "tool": self.tool.pk, "action": "answer"},
        )
        self.assertContains(response, "is using AIX200 now")

    def test_last_use_none(self):
        response = self.client.post(
            reverse("lookup_question_last_use"),
            {"user": self.bob.pk, "tool": self.tool.pk, "action": "answer"},
        )
        self.assertContains(response, "has no usage on AIX200")

    def test_tool_hours(self):
        response = self.client.post(
            reverse("lookup_question_tool_hours"),
            {
                "tool": self.tool.pk,
                "start": "2026-07-01",
                "end": "2026-07-31",
                "action": "answer",
            },
        )
        self.assertContains(response, "ran 2.00 hours across 1 sessions")

    def test_person_hours(self):
        response = self.client.post(
            reverse("lookup_question_person_hours"),
            {
                "user": self.alice.pk,
                "start": "2026-07-01",
                "end": "2026-07-31",
                "action": "answer",
            },
        )
        self.assertContains(response, "used tools for 2.00 hours")

    def test_qualified_on_not_qualified(self):
        response = self.client.post(
            reverse("lookup_question_qualified_on"),
            {"user": self.alice.pk, "tool": self.tool.pk, "action": "answer"},
        )
        self.assertContains(response, "is not qualified on AIX200")

    def test_qualified_on_with_date(self):
        level = QualificationLevel.objects.create(name="Independent", qualify_user=True)
        Qualification.objects.create(
            user=self.alice,
            tool=self.tool,
            qualification_level=level,
            qualified_on=date(2024, 3, 12),
        )
        response = self.client.post(
            reverse("lookup_question_qualified_on"),
            {"user": self.alice.pk, "tool": self.tool.pk, "action": "answer"},
        )
        self.assertContains(response, "was qualified on AIX200")
        self.assertContains(response, "Independent")

    def test_lifetime_hours_all_time(self):
        response = self.client.post(
            reverse("lookup_question_lifetime_hours"),
            {"user": self.alice.pk, "tool": self.tool.pk, "action": "answer"},
        )
        self.assertContains(response, "used AIX200 for 2.00 hours")
        self.assertContains(response, "all time")

    def test_qualifications_list(self):
        Qualification.objects.create(user=self.alice, tool=self.tool, qualified_on=date(2024, 1, 1))
        Qualification.objects.create(user=self.alice, tool=self.tool2, qualified_on=date(2025, 2, 2))
        response = self.client.post(
            reverse("lookup_question_qualifications"),
            {"user": self.alice.pk, "action": "answer"},
        )
        self.assertContains(response, "is qualified on 2 tools")
        self.assertContains(response, "AIX200")
        self.assertContains(response, "SEM")

    def test_qualifications_empty(self):
        response = self.client.post(
            reverse("lookup_question_qualifications"),
            {"user": self.bob.pk, "action": "answer"},
        )
        self.assertContains(response, "is not qualified on any tools")

    def test_download_from_question(self):
        response = self.client.post(
            reverse("lookup_question_lifetime_hours"),
            {"user": self.alice.pk, "tool": self.tool.pk, "action": "download"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("spreadsheetml", response["Content-Type"])
