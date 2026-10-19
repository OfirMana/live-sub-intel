"""Small same-origin adapter for the team's UI; no engine or UI dependency."""
import json
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

from pydantic import ValidationError

from subintel.narrative import NarrativeRequest

MAX_REQUEST_BYTES = 256 * 1024


def make_handler(service, examples=(), html_path: Path | None = None):
    class Handler(BaseHTTPRequestHandler):
        def reply(self, code, payload):
            body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlparse(self.path).path
            if path == '/health':
                return self.reply(200, dict(status='ok', azure_configured=service.planner is not None,
                                            live_provider_verified=False))
            if path == '/api/examples':
                return self.reply(200, list(examples))
            if path == '/' and html_path is not None:
                body = html_path.read_bytes()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                return self.wfile.write(body)
            self.reply(404, dict(error='NOT_FOUND'))

        def do_POST(self):
            if urlparse(self.path).path != '/api/explain':
                return self.reply(404, dict(error='NOT_FOUND'))
            # Local demo API is same-origin; arbitrary browser sites cannot use it.
            origin = self.headers.get('Origin')
            if origin and urlparse(origin).netloc != self.headers.get('Host'):
                return self.reply(403, dict(error='CROSS_ORIGIN_DISABLED'))
            if self.headers.get_content_type() != 'application/json':
                return self.reply(415, dict(error='JSON_REQUIRED'))
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= MAX_REQUEST_BYTES:
                    return self.reply(413, dict(error='INVALID_BODY_SIZE'))
                request = NarrativeRequest.model_validate_json(self.rfile.read(length))
                result = service.explain(request)
            except (ValidationError, ValueError, KeyError, TypeError, IndexError, OverflowError):
                return self.reply(400, dict(error='INVALID_RECOMMENDATION',
                                            detail='Expected a consistent rich demo or legacy Recommendation payload.'))
            self.reply(200, result)

    return Handler
