from music_alert import kuma


class FakeSession:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def get(self, url, params=None, timeout=None):
        import requests
        self.calls.append((url, params))
        if self.fail:
            raise requests.ConnectionError("down")

        class R:
            def raise_for_status(self):
                pass
        return R()


def test_empty_url_does_nothing():
    session = FakeSession()
    assert kuma.push("", True, "ok", session=session) is False
    assert session.calls == []


def test_push_up_and_down():
    session = FakeSession()
    assert kuma.push("http://kuma/api/push/abc", True, "OK", 120, session=session)
    assert kuma.push("http://kuma/api/push/abc", False, "bad", session=session)
    assert session.calls[0][1] == {"status": "up", "msg": "OK", "ping": 120}
    assert session.calls[1][1] == {"status": "down", "msg": "bad"}


def test_push_failure_is_swallowed():
    assert kuma.push("http://kuma/x", True, "ok", session=FakeSession(fail=True)) is False
