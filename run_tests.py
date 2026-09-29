#!/usr/bin/env python
"""Run tests"""
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import django
from django.conf import settings
from django.core.management import execute_from_command_line
from django.test.utils import get_runner

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "NEMO_lookup.tests.test_settings")
    execute_from_command_line(["", "migrate"])
    django.setup()
    TestRunner = get_runner(settings)
    test_runner = TestRunner(interactive=False)
    failures = test_runner.run_tests(["NEMO_lookup.tests"])
    sys.exit(bool(failures))
