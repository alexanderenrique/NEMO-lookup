from importlib.metadata import PackageNotFoundError

from django.apps import AppConfig

# Wheel / PyPI name from pyproject.toml [project].name — NOT the same as AppConfig.name
DISTRIBUTION_NAME = "NEMO-lookup"


class LookupConfig(AppConfig):
    name = "NEMO_lookup"
    label = "lookup"
    verbose_name = "Lookup"
    default_auto_field = "django.db.models.AutoField"

    def ready(self):
        try:
            from NEMO.plugins.utils import check_extra_dependencies
        except ImportError:
            return

        for dist_name in (DISTRIBUTION_NAME, "nemo-lookup"):
            try:
                check_extra_dependencies(dist_name, ["NEMO", "NEMO-CE"])
                return
            except PackageNotFoundError:
                continue
