from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from app.nace_drex import (
    ChoiceAnswer,
    ChoiceQuestion,
    NaceResponseError,
    NoulQuestion,
    decide,
    parse_decision,
    triage_failed_inspection,
)

NACE_KEY = "nace_sk_test_key_not_a_real_secret"
DREX_REQUEST_ID = "req_" + "a" * 32


def _decision_body(team_probability: float = 0.81, escalation_probability: float = 0.91) -> dict:
    return {
        "model": "drex-max-v1.1",
        "answers": {
            "escalate_today": {"type": "noul", "noul": escalation_probability, "confidence": escalation_probability},
            "owning_team": {
                "type": "choice",
                "choice": "maintenance",
                "confidence": team_probability,
                "probabilities": {
                    "quality": round(1 - team_probability - 0.12, 4),
                    "production": 0.08,
                    "maintenance": team_probability,
                    "warehouse": 0.04,
                },
            },
        },
        "usage": {"input_tokens": 120, "output_tokens": 40},
        "evaluation_time_ms": 42.0,
        "request_id": DREX_REQUEST_ID,
    }


def _start_drex(status: int = 200, body: dict | None = None):
    class FakeDrexHandler(BaseHTTPRequestHandler):
        requests: list[dict] = []
        response_status = status
        response_payload = body if body is not None else _decision_body()

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length)
            type(self).requests.append({
                "path": self.path,
                "authorization": self.headers.get("Authorization"),
                "body": json.loads(raw.decode("utf-8")),
            })
            encoded = json.dumps(type(self).response_payload).encode("utf-8")
            self.send_response(type(self).response_status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeDrexHandler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, FakeDrexHandler


def _config(**overrides):
    values = {"nace_api_key": NACE_KEY, "nace_model": "drex-latest"}
    values.update(overrides)
    return SimpleNamespace(**values)


def _stop(server, thread):
    server.shutdown()
    server.server_close()
    thread.join(timeout=1)


def test_decide_posts_typed_questions_and_reads_option_probabilities():
    server, thread, handler = _start_drex()
    try:
        decision = decide(
            {"case": "failed_quality_inspection", "defect_count": 3},
            {
                "escalate_today": NoulQuestion("Does this need escalation today?"),
                "owning_team": ChoiceQuestion("Which team owns this?", {"quality": "Method", "maintenance": "Machine"}),
            },
            config=_config(),
            base_url=f"http://127.0.0.1:{server.server_address[1]}/v1/systemone",
        )
    finally:
        _stop(server, thread)

    assert handler.requests, "Drex decision endpoint was not called"
    sent = handler.requests[0]
    assert sent["path"] == "/v1/systemone"
    assert sent["authorization"] == f"Bearer {NACE_KEY}"
    assert sent["body"]["model"] == "drex-latest"
    assert sent["body"]["state"]["defect_count"] == 3
    assert sent["body"]["questions"]["escalate_today"]["type"] == "noul"
    assert sent["body"]["questions"]["owning_team"]["criteria"]["maintenance"] == "Machine"

    assert decision is not None
    assert decision.model == "drex-max-v1.1"
    assert decision.request_id == DREX_REQUEST_ID
    assert decision.noul("escalate_today").probability == pytest.approx(0.91)
    owning_team = decision.choice("owning_team")
    assert owning_team.route(fallback="quality") == "maintenance"
    assert owning_team.probabilities["maintenance"] == pytest.approx(0.81)


def test_decide_does_not_call_drex_without_an_api_key():
    server, thread, handler = _start_drex()
    try:
        result = decide(
            {"case": "failed_quality_inspection"},
            {"escalate_today": NoulQuestion("Does this need escalation today?")},
            config=_config(nace_api_key=""),
            base_url=f"http://127.0.0.1:{server.server_address[1]}/v1/systemone",
        )
    finally:
        _stop(server, thread)
    assert result is None
    assert handler.requests == []


def test_choice_routing_falls_back_below_the_confidence_threshold():
    answer = ChoiceAnswer(choice="quality", probabilities={"quality": 0.4, "production": 0.35}, confidence=0.4)
    assert answer.route(threshold=0.45, fallback="unassigned") == "unassigned"
    assert answer.route(threshold=0.3, fallback="unassigned") == "quality"
    assert answer.route(threshold=0.5, fallback=None) is None


def test_parse_decision_rejects_probabilities_outside_the_calibrated_range():
    payload = _decision_body()
    payload["answers"]["owning_team"]["probabilities"]["maintenance"] = 1.4
    with pytest.raises(NaceResponseError, match="out-of-range"):
        parse_decision(payload)


def test_decide_reports_rejections_without_echoing_the_upstream_body():
    server, thread, handler = _start_drex(
        status=401,
        body={"error": {"type": "authentication_error", "message": "secret-looking upstream detail"},
              "request_id": DREX_REQUEST_ID},
    )
    try:
        with pytest.raises(NaceResponseError) as excinfo:
            decide(
                {"case": "failed_quality_inspection"},
                {"escalate_today": NoulQuestion("Does this need escalation today?")},
                config=_config(),
                base_url=f"http://127.0.0.1:{server.server_address[1]}/v1/systemone",
            )
    finally:
        _stop(server, thread)
    assert handler.requests
    message = str(excinfo.value)
    assert "401" in message and "authentication_error" in message
    assert "secret-looking upstream detail" not in message
    assert NACE_KEY not in message


def test_triage_routes_the_owning_team_and_escalates_from_high_probability():
    server, thread, handler = _start_drex()
    try:
        triage = triage_failed_inspection(
            inspection_number="QI-1001",
            product_name="Hydraulic valve body",
            defect_count=4,
            sample_size=20,
            notes="Bore diameter above tolerance on four parts.",
            containment_action="Quarantine the lot and stop the cell.",
            on_hold=True,
            config=_config(),
            base_url=f"http://127.0.0.1:{server.server_address[1]}/v1/systemone",
        )
    finally:
        _stop(server, thread)
    assert handler.requests
    state = handler.requests[0]["body"]["state"]
    assert state["defect_rate_percent"] == 20.0
    assert triage is not None
    assert triage.team == "maintenance"
    assert triage.owner == "Maintenance"
    assert triage.urgent is True
    assert triage.escalation_level == "CRITICAL"
    assert triage.team_probability == pytest.approx(0.81)
    assert triage.request_id == DREX_REQUEST_ID


def test_triage_ignores_low_escalation_probability_and_keeps_default_team():
    server, thread, _ = _start_drex(body=_decision_body(team_probability=0.3, escalation_probability=0.2))
    try:
        triage = triage_failed_inspection(
            inspection_number="QI-1002",
            product_name="Bearing housing",
            defect_count=1,
            sample_size=50,
            notes="Cosmetic mark on one part.",
            containment_action="Rework the marked part.",
            on_hold=False,
            config=_config(),
            base_url=f"http://127.0.0.1:{server.server_address[1]}/v1/systemone",
        )
    finally:
        _stop(server, thread)
    assert triage is not None
    assert triage.team == "quality"
    assert triage.urgent is False
    assert triage.escalation_level == "WARNING"


def test_triage_returns_none_when_drex_is_unreachable():
    triage = triage_failed_inspection(
        inspection_number="QI-1003",
        product_name="Gear shaft",
        defect_count=2,
        sample_size=10,
        notes="Runout above tolerance.",
        containment_action="Hold the lot.",
        on_hold=True,
        config=_config(),
        base_url="http://127.0.0.1:1/v1/systemone",
    )
    assert triage is None

