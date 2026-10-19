import json
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from subintel.narrative import NarrativeService
from subintel.narrative_http import make_handler


def test_http_boundary_serves_legacy_recommendation_and_rejects_invalid_bodies():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    rec = json.loads((root / 'docs/examples/recommendation.json').read_text())
    server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(NarrativeService(), [rec], root / 'web/narrative/index.html'))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    def post(body, **headers):
        req = Request(base + '/api/explain', data=body, headers={'Content-Type': 'application/json', **headers})
        try:
            with urlopen(req) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, json.load(error)
    try:
        with urlopen(base + '/health') as response:
            assert json.load(response)['azure_configured'] is False
        with urlopen(base + '/') as response:
            assert b'Evidence explanations' in response.read()
        with urlopen(base + '/api/examples') as response:
            assert json.load(response) == [rec]
        status, result = post(json.dumps(dict(recommendation=rec, language='he')).encode())
        assert status == 200 and result['source'] == 'deterministic_fallback'
        assert result['language'] == 'he'
        assert post(b'{bad json')[0] == 400
        assert post(b'{}', Origin='https://other.example')[0] == 403
        assert post(b'x' * (256 * 1024 + 1))[0] == 413
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
