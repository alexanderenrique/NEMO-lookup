from django.urls import path

from NEMO_lookup import views

urlpatterns = [
    path("lookup/", views.lookup_picker, name="lookup"),
    path("lookup/usage-events/", views.lookup_usage_events, name="lookup_usage_events"),
    path("lookup/reservations/", views.lookup_reservations, name="lookup_reservations"),
    path("lookup/users/", views.lookup_users, name="lookup_users"),
    path("lookup/questions/last-use/", views.question_last_use, name="lookup_question_last_use"),
    path("lookup/questions/tool-hours/", views.question_tool_hours, name="lookup_question_tool_hours"),
    path("lookup/questions/person-hours/", views.question_person_hours, name="lookup_question_person_hours"),
    path("lookup/questions/qualified-on/", views.question_qualified_on, name="lookup_question_qualified_on"),
    path(
        "lookup/questions/lifetime-hours/",
        views.question_lifetime_hours,
        name="lookup_question_lifetime_hours",
    ),
    path(
        "lookup/questions/qualifications/",
        views.question_qualifications,
        name="lookup_question_qualifications",
    ),
    path("lookup/search/users/", views.search_users, name="lookup_search_users"),
    path("lookup/search/tools/", views.search_tools, name="lookup_search_tools"),
]
