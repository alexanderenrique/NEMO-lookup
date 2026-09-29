from datetime import date

from django import forms

from NEMO.models import Project, Tool, User, UserType
from NEMO_lookup.exports import previous_month_range


class DateRangeFormMixin(forms.Form):
    start = forms.DateField(
        required=True,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        help_text="Required.",
    )
    end = forms.DateField(
        required=True,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        help_text="Required.",
    )

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start")
        end = cleaned.get("end")
        if start and end and end < start:
            self.add_error("end", "End date must be on or after the start date.")
        return cleaned

    @classmethod
    def default_previous_month(cls):
        start, end = previous_month_range()
        return cls(initial={"start": start, "end": end})


class UsageEventsFilterForm(DateRangeFormMixin):
    user_type = forms.ModelChoiceField(
        queryset=UserType.objects.all(),
        required=False,
        empty_label="All user types",
        widget=forms.Select(attrs={"class": "form-control"}),
        help_text="Optional. Leave as All user types to include every type.",
    )
    tool = forms.ModelChoiceField(
        queryset=Tool.objects.filter(visible=True).order_by("name"),
        required=False,
        empty_label="All tools",
        widget=forms.Select(attrs={"class": "form-control"}),
        help_text="Optional. Leave as All tools to include every tool.",
    )
    project = forms.ModelChoiceField(
        queryset=Project.objects.all().order_by("name"),
        required=False,
        empty_label="All projects",
        widget=forms.Select(attrs={"class": "form-control"}),
        help_text="Optional. Leave as All projects to include every project.",
    )


class ReservationsFilterForm(DateRangeFormMixin):
    STATUS_CHOICES = [
        ("all", "All"),
        ("not_cancelled", "Not cancelled"),
        ("cancelled", "Cancelled"),
        ("missed", "Missed"),
    ]
    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        required=False,
        initial="all",
        widget=forms.Select(attrs={"class": "form-control"}),
        help_text="Optional. Leave as All to include every status.",
    )
    user_type = forms.ModelChoiceField(
        queryset=UserType.objects.all(),
        required=False,
        empty_label="All user types",
        widget=forms.Select(attrs={"class": "form-control"}),
        help_text="Optional. Leave as All user types to include every type.",
    )
    tool = forms.ModelChoiceField(
        queryset=Tool.objects.filter(visible=True).order_by("name"),
        required=False,
        empty_label="All tools and areas",
        widget=forms.Select(attrs={"class": "form-control"}),
        help_text="Optional. Leave as All tools and areas to include every reservation.",
    )
    project = forms.ModelChoiceField(
        queryset=Project.objects.all().order_by("name"),
        required=False,
        empty_label="All projects",
        widget=forms.Select(attrs={"class": "form-control"}),
        help_text="Optional. Leave as All projects to include every project.",
    )


class UsersFilterForm(forms.Form):
    ACCOUNT_CHOICES = [
        ("all", "All"),
        ("active", "Active"),
        ("inactive", "Inactive"),
    ]
    ROLE_CHOICES = [
        ("all", "All"),
        ("staff", "Staff"),
        ("user_office", "User office"),
        ("facility_manager", "Facility manager"),
        ("accounting_officer", "Accounting officer"),
        ("service_personnel", "Service personnel"),
    ]
    ACCESS_CHOICES = [
        ("any", "Any"),
        ("expired", "Expired"),
        ("not_expired", "Not expired"),
    ]
    user_type = forms.ModelChoiceField(
        queryset=UserType.objects.all(),
        required=False,
        empty_label="All user types",
        widget=forms.Select(attrs={"class": "form-control"}),
        help_text="Optional. Leave as All user types to include every type.",
    )
    account = forms.ChoiceField(
        choices=ACCOUNT_CHOICES,
        required=False,
        initial="all",
        widget=forms.Select(attrs={"class": "form-control"}),
        help_text="Optional. Leave as All to include active and inactive accounts.",
    )
    role = forms.ChoiceField(
        choices=ROLE_CHOICES,
        required=False,
        initial="all",
        widget=forms.Select(attrs={"class": "form-control"}),
        help_text="Optional. Leave as All to include every role.",
    )
    access = forms.ChoiceField(
        choices=ACCESS_CHOICES,
        required=False,
        initial="any",
        widget=forms.Select(attrs={"class": "form-control"}),
        help_text="Optional. Leave as Any to include expired and current access.",
    )


class PersonToolForm(forms.Form):
    user = forms.ModelChoiceField(queryset=User.objects.all(), widget=forms.HiddenInput())
    tool = forms.ModelChoiceField(queryset=Tool.objects.filter(visible=True), widget=forms.HiddenInput())
    user_display = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "id": "user_search", "autocomplete": "off"}),
        label="Lab member",
        help_text="Required.",
    )
    tool_display = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "id": "tool_search", "autocomplete": "off"}),
        label="Tool",
        help_text="Required.",
    )


class ToolDateRangeForm(forms.Form):
    tool = forms.ModelChoiceField(queryset=Tool.objects.filter(visible=True), widget=forms.HiddenInput())
    tool_display = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "id": "tool_search", "autocomplete": "off"}),
        label="Tool",
        help_text="Required.",
    )
    start = forms.DateField(
        required=True,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        help_text="Required.",
    )
    end = forms.DateField(
        required=True,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        help_text="Required.",
    )

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start")
        end = cleaned.get("end")
        if start and end and end < start:
            self.add_error("end", "End date must be on or after the start date.")
        return cleaned

    @classmethod
    def default_previous_month(cls):
        start, end = previous_month_range()
        return cls(initial={"start": start, "end": end})


class PersonDateRangeToolForm(forms.Form):
    user = forms.ModelChoiceField(queryset=User.objects.all(), widget=forms.HiddenInput())
    user_display = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "id": "user_search", "autocomplete": "off"}),
        label="Lab member",
        help_text="Required.",
    )
    start = forms.DateField(
        required=True,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        help_text="Required.",
    )
    end = forms.DateField(
        required=True,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        help_text="Required.",
    )
    tool = forms.ModelChoiceField(
        queryset=Tool.objects.filter(visible=True),
        required=False,
        widget=forms.HiddenInput(),
    )
    tool_display = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "id": "tool_search", "autocomplete": "off"}),
        label="Tool",
        help_text="Optional. Leave blank to include every tool.",
    )

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start")
        end = cleaned.get("end")
        if start and end and end < start:
            self.add_error("end", "End date must be on or after the start date.")
        return cleaned

    @classmethod
    def default_previous_month(cls):
        start, end = previous_month_range()
        return cls(initial={"start": start, "end": end})


class PersonToolOptionalDatesForm(forms.Form):
    """Lab member + tool; dates optional (blank = all time)."""

    user = forms.ModelChoiceField(queryset=User.objects.all(), widget=forms.HiddenInput())
    tool = forms.ModelChoiceField(queryset=Tool.objects.filter(visible=True), widget=forms.HiddenInput())
    user_display = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "id": "user_search", "autocomplete": "off"}),
        label="Lab member",
        help_text="Required.",
    )
    tool_display = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "id": "tool_search", "autocomplete": "off"}),
        label="Tool",
        help_text="Required.",
    )
    start = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        label="Start",
        help_text="Optional. Leave both dates blank to include all time.",
    )
    end = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        label="End",
        help_text="Optional. Leave both dates blank to include all time.",
    )

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start")
        end = cleaned.get("end")
        if (start and not end) or (end and not start):
            self.add_error("end" if start else "start", "Provide both start and end, or leave both blank for all time.")
        if start and end and end < start:
            self.add_error("end", "End date must be on or after the start date.")
        return cleaned


class PersonOnlyForm(forms.Form):
    user = forms.ModelChoiceField(queryset=User.objects.all(), widget=forms.HiddenInput())
    user_display = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "id": "user_search", "autocomplete": "off"}),
        label="Lab member",
        help_text="Required.",
    )


def filter_summary_from_cleaned(cleaned: dict) -> str:
    parts = []
    for key, value in cleaned.items():
        if key.endswith("_display") or value in (None, "", []):
            continue
        if isinstance(value, date):
            parts.append(f"{key}={value.isoformat()}")
        elif hasattr(value, "pk"):
            parts.append(f"{key}={value}")
        else:
            parts.append(f"{key}={value}")
    return "; ".join(parts)
