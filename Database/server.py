from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import sqlite3
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "qdr_shift_history.sqlite3"
HOST = "0.0.0.0"
PORT = 8765


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS shift_snapshots (
                id TEXT PRIMARY KEY,
                saved_at TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )


def read_snapshots():
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT payload FROM shift_snapshots ORDER BY saved_at ASC"
        ).fetchall()
    return [json.loads(row[0]) for row in rows]


def replace_snapshots(items):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM shift_snapshots")
        conn.executemany(
            "INSERT OR REPLACE INTO shift_snapshots (id, saved_at, payload) VALUES (?, ?, ?)",
            [
                (
                    str(item.get("id", "")),
                    str(item.get("savedAt", "")),
                    json.dumps(item, separators=(",", ":")),
                )
                for item in items
                if item.get("id") and item.get("savedAt")
            ],
        )


class QdrHandler(SimpleHTTPRequestHandler):
    server_version = "QDRPassdownServer/1.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            self.path = "/QDR Auto Email.html"
            return super().do_GET()
        if path == "/api/shift-history":
            return self.write_json(read_snapshots())
        return super().do_GET()

    def do_PUT(self):
        path = urlparse(self.path).path
        if path != "/api/shift-history":
            self.send_error(404, "Unknown API endpoint")
            return
        try:
            payload = self.read_json_body()
            if not isinstance(payload, list):
                raise ValueError("Expected a JSON array")
            replace_snapshots(payload[-24:])
            self.write_json(read_snapshots())
        except Exception as exc:
            self.write_json({"error": str(exc)}, status=400)

    def do_DELETE(self):
        path = urlparse(self.path).path
        if path != "/api/shift-history":
            self.send_error(404, "Unknown API endpoint")
            return
        replace_snapshots([])
        self.write_json([])

    def read_json_body(self):
        size = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(size).decode("utf-8")
        return json.loads(raw or "null")

    def write_json(self, payload, status=200):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    mimetypes.add_type("text/html; charset=utf-8", ".html")
    init_db()
    server = ThreadingHTTPServer((HOST, PORT), QdrHandler)
    print(f"QDR dashboard server running at http://localhost:{PORT}")
    print(f"Shared shift history database: {DB_PATH}")
    server.serve_forever()
