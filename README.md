# NEMO Lookup

Plugin for [NEMO](https://github.com/usnistgov/NEMO) (and NEMO-CE) that lets staff and other permitted users **download facility data as Excel** and **answer common questions** by picking lab members and tools by name. Queries use the Django ORM inside NEMO. Nothing calls the HTTP API.

Requires **NEMO or NEMO-CE ≥ 7.3.0** and **Python ≥ 3.10**.

## Features

### Downloads

- **Usage events** — date range, optional user type / tool / project
- **Reservations** — date range, status (all / not cancelled / cancelled / missed), optional filters
- **Users** — user type, active/inactive, role, access expiration

Spreadsheets use lab member names, tool names, project and account names. Times are in the site timezone.

### Common questions

- When did this lab member last use this tool?
- How many hours did this tool run in this period?
- How many hours did this lab member use tools in this period?
- When was this lab member qualified on this tool?
- How many hours has this lab member used this tool? (optional date range; blank = all time)
- Which tools is this lab member qualified on?

Each question answers in a sentence, shows a table, and can download those rows.

## Install

```bash
pip install NEMO-lookup
# or in Docker: NEMO_EXTRA_PIP_PACKAGES="NEMO-lookup"
```

In site `settings.py`, list the plugin **before** `NEMO` so the navbar override wins:

```python
INSTALLED_APPS = [
    "NEMO_lookup.apps.LookupConfig",  # before NEMO
    "NEMO",
    ...
]
```

Then:

```bash
python manage.py migrate lookup
```

### Permissions

Access requires **`lookup | Can use lookup`**.

Django superusers pass this automatically. Other staff see **Lookup** under Administration after you grant the permission on the user or a group (Detailed Admin → Users / Groups).

The Django admin add/change/delete/view permissions on the Lookup log only control the audit log in admin. They do not open the feature.

### Landing page icon

Detailed Admin → Landing page choices → add an entry with URL `/lookup/` and a 128×128 image.

## Development

```bash
pip install -e ".[NEMO-CE]"
# or point PYTHONPATH / venv at a local NEMO-CE checkout
python run_tests.py
```

## Usage

1. Open **Lookup** (`/lookup/`) from Administration.
2. Choose a download category or a common question.
3. Set filters or pick a lab member/tool by name, then Download or Answer.
