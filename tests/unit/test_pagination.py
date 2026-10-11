from starlette.requests import Request
from clubledger.presentation.pagination import paginate


def request(query):
    return Request({"type": "http", "scheme": "https", "server": ("test", 443),
                    "path": "/admin/events", "query_string": query.encode(), "headers": []})


def test_pages_preserve_filters_and_never_lose_rows():
    rows = list(range(45))
    result, info = paginate(request("page=2&event_search=photo"), rows)
    assert result == list(range(20, 40))
    assert info["pages"] == 3
    assert "event_search=photo" in info["next"]
    assert "page=3" in info["next"]
    assert paginate(request("page=999"), rows)[0] == list(range(40, 45))


def test_invalid_and_empty_pages():
    assert paginate(request("page=bad"), [1])[0] == [1]
    rows, info = paginate(request("page=-5"), [])
    assert rows == [] and info["start"] == 0 and info["page"] == 1
