import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "src", "data_generation"))
sys.path.insert(0, os.path.join(REPO_ROOT, "src", "governance"))
sys.path.insert(0, os.path.join(REPO_ROOT, "tests"))

import emulator  # noqa: E402
import generate  # noqa: E402
import reference  # noqa: E402


@pytest.fixture(scope="session")
def landing_dir(tmp_path_factory):
    out = tmp_path_factory.mktemp("landing")
    generate.generate(str(out))
    return str(out)


@pytest.fixture(scope="session")
def expected_rows(landing_dir):
    return reference.expected_metrics(landing_dir)


@pytest.fixture(scope="session")
def run(landing_dir, expected_rows):
    """The whole pipeline (bronze to gold) executed locally, plus qa.expected_kpis."""
    return emulator.run_pipeline(landing_dir, expected_rows)
