import httpx
import pytest

from cs2bot.llm.ollama import OllamaBackend


@pytest.mark.parametrize(
    ("exc", "needle"),
    [
        (httpx.ReadTimeout(""), "no answer from http://10.0.0.5:11434 within 30.0s"),
        (httpx.ConnectError(""), "nothing is listening at http://10.0.0.5:11434"),
        (
            httpx.RemoteProtocolError("peer closed"),
            "RemoteProtocolError talking to http://10.0.0.5:11434: peer closed",
        ),
    ],
)
def test_blank_httpx_errors_still_say_what_went_wrong(exc, needle):
    backend = OllamaBackend(base_url="http://10.0.0.5:11434/", model="m")
    assert backend._why(exc) == needle
