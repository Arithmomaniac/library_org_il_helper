import pytest


@pytest.fixture
def membership_json():
    return {
        "idNo": "000000018",
        "dBName": "example",
        "libraryName": "Example Library",
        "allowExtension": True,
    }


@pytest.fixture
def loan_json():
    return {
        "idNo": 77,
        "copyNo": 123,
        "titleName": "An overdue book",
        "authorName": "Example Author",
        "dateBorrowed": "2026-09-01T00:00:00",
        "datePromise": "2026-10-23T00:00:00",
        "dateReturn": None,
        "dateExtend": None,
        "isReserved": False,
        "daysLeft": -3,
    }
