import pytest


def pytest_addoption(parser):
    parser.addoption("--integration", action="store_true", default=False, help="Run integration tests")


def pytest_collection_modifyitems(config, items):
    run_integration = config.getoption("--integration")
    args = [str(a) for a in config.args]
    targeting_integration = any("integration" in a for a in args)

    if not run_integration and not targeting_integration:
        skip = pytest.mark.skip(reason="pass --integration to run or target tests/integration/ directly")
        for item in items:
            if "integration" in str(item.fspath):
                item.add_marker(skip)
