import pytest

from src.gitlab.client import GitLabClient, GitLabError


class _Resp:
    def __init__(self, status_code: int, data=None, text: str = ""):
        self.status_code = status_code
        self._data = data
        self.text = text

    def json(self):
        if isinstance(self._data, Exception):
            raise self._data
        return self._data


class _Sess:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def request(self, method, url, headers=None, params=None, data=None, timeout=None):
        self.calls.append((method, url, params, data))
        key = (method, url)
        if key not in self.routes:
            return _Resp(404, {"message": "Not Found"}, text="Not Found")
        resp = self.routes[key]
        if callable(resp):
            return resp(method, url, params, data)
        return resp


def test_get_project_by_path_not_found(monkeypatch):
    monkeypatch.setenv("GITLAB_TOKEN", "t")
    monkeypatch.setenv("GITLAB_BASE_URL", "https://git.example")

    s = _Sess({})
    gl = GitLabClient.from_env(session=s)
    p = gl.get_project_by_path("amicable/missing")
    assert p is None


def test_create_project_success(monkeypatch):
    monkeypatch.setenv("GITLAB_TOKEN", "t")
    monkeypatch.setenv("GITLAB_BASE_URL", "https://git.example")

    url = "https://git.example/api/v4/projects"
    routes = {
        ("POST", url): _Resp(
            200,
            {
                "id": 1,
                "name": "My App",
                "path": "my-app",
                "path_with_namespace": "amicable/my-app",
                "web_url": "https://git.example/amicable/my-app",
                "http_url_to_repo": "https://git.example/amicable/my-app.git",
            },
        )
    }
    s = _Sess(routes)
    gl = GitLabClient.from_env(session=s)
    p = gl.create_project(namespace_id=2, name="My App", path="my-app")
    assert p.id == 1
    assert p.path_with_namespace == "amicable/my-app"


def test_create_project_path_taken(monkeypatch):
    monkeypatch.setenv("GITLAB_TOKEN", "t")
    monkeypatch.setenv("GITLAB_BASE_URL", "https://git.example")

    url = "https://git.example/api/v4/projects"
    routes = {
        ("POST", url): _Resp(400, {"message": {"path": ["has already been taken"]}})
    }
    s = _Sess(routes)
    gl = GitLabClient.from_env(session=s)
    with pytest.raises(GitLabError) as e:
        gl.create_project(namespace_id=2, name="My App", path="my-app")
    assert e.value.status_code == 400
