#!/usr/bin/env python3
"""
Price Alert Tool - Web Interface Server
---------------------------------------
A zero-dependency local web server built with Python's standard `http.server`.
Provides an interactive dashboard to inspect price series, moving averages,
crossing thresholds, and fired alerts.

Usage:
    python web_server.py [port]
    or:
    python alerts.py --web
"""

import io
import json
import os
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from alerts import (
    Alert,
    calculate_sma_series,
    evaluate_all_rules,
    parse_prices_csv,
    parse_rules_json,
)

PORT = 8000
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, "web")


def build_analysis_payload(prices_by_instrument, rules):
    """Build structured data for UI table and interactive chart."""
    alerts = evaluate_all_rules(prices_by_instrument, rules)
    cli_lines = [a.to_output_line() for a in alerts]

    # Build per-instrument chart data
    instruments_data = {}
    for inst, points in prices_by_instrument.items():
        closes = [p.close for p in points]
        dates = [p.date for p in points]

        # Calculate any SMA requested by rules for this instrument
        inst_rules = [r for r in rules if r["instrument"] == inst]
        smas = {}
        for r in inst_rules:
            if r["type"] == "ma_cross":
                for w in (r["short"], r["long"]):
                    key = f"sma_{w}"
                    if key not in smas:
                        smas[key] = calculate_sma_series(closes, w)

        instruments_data[inst] = {
            "dates": dates,
            "closes": closes,
            "smas": smas,
            "rules": inst_rules,
        }

    alerts_list = [
        {
            "date": a.date,
            "rule_id": a.rule_id,
            "instrument": a.instrument,
            "rule_type": a.rule_type,
            "details": a.details,
            "line": a.to_output_line(),
        }
        for a in alerts
    ]

    return {
        "success": True,
        "alerts": alerts_list,
        "cli_output": "\n".join(cli_lines),
        "total_alerts": len(alerts),
        "instruments": instruments_data,
        "rules": rules,
    }


class AlertDashboardHandler(BaseHTTPRequestHandler):

    def send_json(self, status: int, data: dict):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_static(self, filename: str, content_type: str):
        filepath = os.path.join(WEB_DIR, filename)
        if not os.path.exists(filepath):
            self.send_error(404, f"File not found: {filename}")
            return
        with open(filepath, "rb") as f:
            content = f.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        url = urlparse(self.path)
        path = url.path

        if path in ("/", "/index.html"):
            self.serve_static("index.html", "text/html; charset=utf-8")
        elif path == "/styles.css":
            self.serve_static("styles.css", "text/css; charset=utf-8")
        elif path == "/app.js":
            self.serve_static("app.js", "application/javascript; charset=utf-8")
        elif path == "/api/default":
            # Load default sample files from disk
            prices_path = os.path.join(BASE_DIR, "prices.csv")
            rules_path = os.path.join(BASE_DIR, "rules.json")
            try:
                prices = parse_prices_csv(prices_path)
                rules = parse_rules_json(rules_path)
                payload = build_analysis_payload(prices, rules)
                self.send_json(200, payload)
            except Exception as e:
                self.send_json(500, {"success": False, "error": str(e)})
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        url = urlparse(self.path)
        if url.path == "/api/evaluate":
            content_length = int(self.headers.get("Content-Length", 0))
            post_body = self.rfile.read(content_length).decode("utf-8")
            try:
                data = json.loads(post_body)
                csv_text = data.get("prices_csv", "")
                rules_json = data.get("rules_json", [])

                prices_stream = io.StringIO(csv_text)
                prices = parse_prices_csv(prices_stream)

                if isinstance(rules_json, str):
                    rules_stream = io.StringIO(rules_json)
                    rules = parse_rules_json(rules_stream)
                else:
                    rules_stream = io.StringIO(json.dumps(rules_json))
                    rules = parse_rules_json(rules_stream)

                payload = build_analysis_payload(prices, rules)
                self.send_json(200, payload)
            except Exception as e:
                self.send_json(400, {"success": False, "error": str(e)})
        else:
            self.send_error(404, "Endpoint not found")

    def log_message(self, format, *args):
        # Clean terminal logging
        sys.stderr.write(f"[HTTP] {self.address_string()} - {format % args}\n")


def start_server(port: int = PORT, open_browser: bool = False):
    os.makedirs(WEB_DIR, exist_ok=True)
    server_address = ("127.0.0.1", port)
    httpd = ThreadingHTTPServer(server_address, AlertDashboardHandler)
    url = f"http://localhost:{port}"
    print(f"\n=======================================================")
    print(f" Price Alert Tool - Clean Human UI Dashboard")
    print(f" Serving at: {url}")
    print(f" Press Ctrl+C to stop")
    print(f"=======================================================\n")
    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
        httpd.server_close()


if __name__ == "__main__":
    p = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else PORT
    start_server(p, open_browser=False)
