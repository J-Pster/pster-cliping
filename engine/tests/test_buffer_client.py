import pytest

from clipador.publish.buffer_client import graphql_request
from clipador.publish.models import PublishError


class _FakeResponse:
    def __init__(self, *, status_code=200, json_data=None, text="", headers=None):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text
        self.headers = headers or {}
        self.ok = 200 <= status_code < 300

    def json(self):
        return self._json_data


def test_graphql_request_sem_api_key_levanta_publish_error(monkeypatch):
    monkeypatch.delenv("BUFFER_API_KEY", raising=False)

    with pytest.raises(PublishError, match="BUFFER_API_KEY"):
        graphql_request("query { account { organizations { id } } }")


def test_graphql_request_trata_errors_no_corpo(monkeypatch, mocker):
    monkeypatch.setenv("BUFFER_API_KEY", "token")
    mocker.patch(
        "clipador.publish.buffer_client.requests.post",
        return_value=_FakeResponse(json_data={"errors": [{"message": "canal invalido"}]}),
    )

    with pytest.raises(PublishError, match="canal invalido"):
        graphql_request("query { account { organizations { id } } }")


def test_graphql_request_trata_429(monkeypatch, mocker):
    monkeypatch.setenv("BUFFER_API_KEY", "token")
    mocker.patch(
        "clipador.publish.buffer_client.requests.post",
        return_value=_FakeResponse(
            status_code=429,
            json_data={"extensions": {"window": "15m"}},
            headers={"Retry-After": "60"},
        ),
    )

    with pytest.raises(PublishError, match="429"):
        graphql_request("query { account { organizations { id } } }")


def test_graphql_request_retorna_data_no_caminho_feliz(monkeypatch, mocker):
    monkeypatch.setenv("BUFFER_API_KEY", "token")
    mocker.patch(
        "clipador.publish.buffer_client.requests.post",
        return_value=_FakeResponse(json_data={"data": {"account": {"organizations": [{"id": "org_1"}]}}}),
    )

    data = graphql_request("query { account { organizations { id } } }")

    assert data == {"account": {"organizations": [{"id": "org_1"}]}}
