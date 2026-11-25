"""Calibrated decision support through the Nace Drex decision API.

FactoryLink asks Drex a small set of typed questions about one case and routes
the case using the probability returned for each option, instead of trusting a
single label. The integration is optional: when NACE_API_KEY is empty the
helpers return None and the caller keeps its existing behaviour, and a Drex
failure never blocks a quality record from being created.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from math import isfinite
from typing import Any, Mapping

from .config import settings

logger = logging.getLogger(__name__)

DREX_ENDPOINT = "https://console.nace.ai/v1/systemone"
DREX_TIMEOUT_SECONDS = 8.0
MAX_REQUEST_BYTES = 4_194_304
MAX_RESPONSE_BYTES = 8_388_608
DEFAULT_ROUTE_THRESHOLD = 0.5
URGENT_ESCALATION_THRESHOLD = 0.7


class NaceError(RuntimeError):
    """Base class for Drex integration failures."""


class NaceConfigError(NaceError):
    """Raised when a decision request cannot be built or is out of bounds."""


class NaceResponseError(NaceError):
    """Raised when Drex rejects a request or returns an unusable response."""


@dataclass(frozen=True)
class NoulQuestion:
    """Yes-or-no question; Drex answers with the probability of yes."""

    instructions: str

    def payload(self) -> dict[str, Any]:
        text = self.instructions.strip()
        if not text:
            raise NaceConfigError("A Drex noul question requires instructions.")
        return {"type": "noul", "instructions": text}


@dataclass(frozen=True)
class ChoiceQuestion:
    """One-of-many question; Drex answers with a probability per option."""

    instructions: str
    criteria: Mapping[str, str]

    def payload(self) -> dict[str, Any]:
        text = self.instructions.strip()
        if not text:
            raise NaceConfigError("A Drex choice question requires instructions.")
        criteria = {
            str(label).strip(): str(description).strip()
            for label, description in self.criteria.items()
            if str(label).strip()
        }
        if len(criteria) < 2:
            raise NaceConfigError("A Drex choice question requires at least two labelled options.")
        return {"type": "choice", "instructions": text, "criteria": criteria}


Question = NoulQuestion | ChoiceQuestion


def _probability(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise NaceResponseError(f"Drex returned a non-numeric {field}.") from exc
    if not isfinite(number) or not 0.0 <= number <= 1.0:
        raise NaceResponseError(f"Drex returned an out-of-range {field}.")
    return number


@dataclass(frozen=True)
class NoulAnswer:
    probability: float
    confidence: float


@dataclass(frozen=True)
class ChoiceAnswer:
    choice: str
    probabilities: Mapping[str, float]
    confidence: float

    def route(self, *, threshold: float = DEFAULT_ROUTE_THRESHOLD, fallback: str | None = None) -> str | None:
        """Return the most probable option when it clears ``threshold``.

        A label that is merely ahead of the others is not enough on its own;
        below the threshold the caller's ``fallback`` (or ``None``) is used.
        """
        if not self.probabilities:
            return fallback
        best = max(self.probabilities, key=self.probabilities.get)
        return best if self.probabilities[best] >= threshold else fallback


@dataclass(frozen=True)
class DrexDecision:
    model: str
    request_id: str
    answers: Mapping[str, NoulAnswer | ChoiceAnswer]
    usage: Mapping[str, int]

    def noul(self, question_id: str) -> NoulAnswer:
        answer = self.answers.get(question_id)
        if not isinstance(answer, NoulAnswer):
            raise NaceResponseError(f"Drex did not return a noul answer for '{question_id}'.")
        return answer

    def choice(self, question_id: str) -> ChoiceAnswer:
        answer = self.answers.get(question_id)
        if not isinstance(answer, ChoiceAnswer):
            raise NaceResponseError(f"Drex did not return a choice answer for '{question_id}'.")
        return answer


def parse_decision(payload: Any) -> DrexDecision:
    """Validate a Drex response body and its calibrated probabilities."""
    if not isinstance(payload, dict):
        raise NaceResponseError("Drex returned a response that is not an object.")
    raw_answers = payload.get("answers")
    if not isinstance(raw_answers, dict) or not raw_answers:
        raise NaceResponseError("Drex returned no answers.")
    answers: dict[str, NoulAnswer | ChoiceAnswer] = {}
    for question_id, raw in raw_answers.items():
        if not isinstance(raw, dict):
            raise NaceResponseError(f"Drex returned a malformed answer for '{question_id}'.")
        kind = raw.get("type")
        if kind == "noul":
            probability = _probability(raw.get("noul"), "noul probability")
            answers[str(question_id)] = NoulAnswer(
                probability=probability,
                confidence=_probability(raw.get("confidence", probability), "noul confidence"),
            )
        elif kind == "choice":
            raw_probabilities = raw.get("probabilities")
            if not isinstance(raw_probabilities, dict) or not raw_probabilities:
                raise NaceResponseError(f"Drex returned no option probabilities for '{question_id}'.")
            probabilities = {
                str(label): _probability(value, "option probability")
                for label, value in raw_probabilities.items()
            }
            choice = str(raw.get("choice") or max(probabilities, key=probabilities.get))
            if choice not in probabilities:
                raise NaceResponseError(f"Drex chose an undefined option for '{question_id}'.")
            answers[str(question_id)] = ChoiceAnswer(
                choice=choice,
                probabilities=probabilities,
                confidence=_probability(raw.get("confidence", probabilities[choice]), "choice confidence"),
            )
        else:
            raise NaceResponseError(f"Drex returned an unsupported answer type for '{question_id}'.")
    usage_raw = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    usage = {str(key): int(value) for key, value in usage_raw.items() if isinstance(value, int)}
    return DrexDecision(
        model=str(payload.get("model") or ""),
        request_id=str(payload.get("request_id") or ""),
        answers=answers,
        usage=usage,
    )


def _http_error_message(exc: urllib.error.HTTPError) -> str:
    kind, request_id, retry_after = "error", "", ""
    try:
        envelope = json.loads(exc.read(8192).decode("utf-8"))
        error = envelope.get("error") if isinstance(envelope, dict) else None
        if isinstance(error, dict):
            kind = str(error.get("type") or kind)
        if isinstance(envelope, dict):
            request_id = str(envelope.get("request_id") or "")
    except Exception:
        pass
    try:
        retry_after = str(exc.headers.get("retry-after-ms") or "") if exc.headers else ""
    except Exception:
        retry_after = ""
    message = f"Drex rejected the request with HTTP {exc.code} ({kind})."
    if retry_after:
        message = f"{message} Retry after {retry_after} ms."
    if request_id:
        message = f"{message} Request {request_id}."
    return message


def decide(
    state: Any,
    questions: Mapping[str, Question],
    *,
    config: Any = settings,
    base_url: str = DREX_ENDPOINT,
    timeout: float = DREX_TIMEOUT_SECONDS,
) -> DrexDecision | None:
    """Ask Drex the typed questions about ``state`` and return its answers.

    Returns ``None`` when no API key is configured, so the feature stays off
    until an operator provides one. Transport and response failures raise
    ``NaceError``; callers that treat routing as optional should catch it.
    """
    api_key = str(getattr(config, "nace_api_key", "") or "").strip()
    if not api_key:
        return None
    if not isinstance(questions, Mapping) or not questions:
        raise NaceConfigError("A Drex decision requires at least one question.")
    encoded_questions: dict[str, dict[str, Any]] = {}
    for question_id, question in questions.items():
        if not isinstance(question, (NoulQuestion, ChoiceQuestion)):
            raise NaceConfigError("Drex questions must be NoulQuestion or ChoiceQuestion instances.")
        if not str(question_id).strip():
            raise NaceConfigError("Drex question ids must not be empty.")
        encoded_questions[str(question_id)] = question.payload()
    body = json.dumps(
        {
            "model": str(getattr(config, "nace_model", "") or "drex-latest").strip(),
            "state": state,
            "questions": encoded_questions,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    if len(body) > MAX_REQUEST_BYTES:
        raise NaceConfigError("The Drex decision request exceeds the 4 MB API limit.")
    request = urllib.request.Request(
        base_url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise NaceResponseError(_http_error_message(exc)) from exc
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise NaceResponseError("The Drex decision service is unavailable.") from exc
    if len(raw) > MAX_RESPONSE_BYTES:
        raise NaceResponseError("Drex returned an oversized response.")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise NaceResponseError("Drex returned an unreadable response.") from exc
    return parse_decision(payload)


CASE_TEAM_LABELS: dict[str, str] = {
    "quality": "Quality",
    "production": "Production",
    "maintenance": "Maintenance",
    "warehouse": "Warehouse",
}

CASE_TEAM_CRITERIA: dict[str, str] = {
    "quality": "Inspection method, sampling plan, specification or release-decision problems",
    "production": "Process parameters, operator method or defects introduced during manufacturing",
    "maintenance": "Machine condition, tooling wear, calibration or equipment breakdown",
    "warehouse": "Storage, handling, labelling or mix-ups of received material or finished goods",
}


@dataclass(frozen=True)
class InspectionTriage:
    """Routing suggested for a failed quality inspection."""

    team: str
    owner: str
    urgent: bool
    team_probability: float
    escalation_level: str
    request_id: str


def triage_failed_inspection(
    *,
    inspection_number: str,
    product_name: str,
    defect_count: int,
    sample_size: int,
    notes: str,
    containment_action: str,
    on_hold: bool,
    config: Any = settings,
    base_url: str = DREX_ENDPOINT,
) -> InspectionTriage | None:
    """Route a failed inspection with Drex's option probabilities.

    Returns ``None`` when Drex is not configured or does not answer, leaving
    the caller's default CAPA assignment untouched.
    """
    defect_rate = round(defect_count / sample_size * 100, 2) if sample_size > 0 else None
    decision = None
    try:
        decision = decide(
            {
                "case": "failed_quality_inspection",
                "inspection_number": inspection_number,
                "product": product_name,
                "defect_count": defect_count,
                "sample_size": sample_size,
                "defect_rate_percent": defect_rate,
                "material_or_product_on_hold": bool(on_hold),
                "inspector_notes": notes[:4000],
                "containment_action": containment_action[:2000],
            },
            {
                "escalate_today": NoulQuestion(
                    "Does this non-conformance need escalation to plant management today "
                    "rather than the usual review cycle?"
                ),
                "owning_team": ChoiceQuestion(
                    "Which team should own the corrective action for this non-conformance?",
                    criteria=dict(CASE_TEAM_CRITERIA),
                ),
            },
            config=config,
            base_url=base_url,
        )
    except NaceError as exc:
        logger.warning("nace_inspection_triage_unavailable: %s", exc)
        return None
    if decision is None:
        return None
    try:
        team_answer = decision.choice("owning_team")
        urgent_answer = decision.noul("escalate_today")
    except NaceResponseError as exc:
        logger.warning("nace_inspection_triage_unusable: %s", exc)
        return None
    team = team_answer.route(fallback="quality") or "quality"
    urgent = urgent_answer.probability >= URGENT_ESCALATION_THRESHOLD
    return InspectionTriage(
        team=team,
        owner=CASE_TEAM_LABELS[team],
        urgent=urgent,
        team_probability=team_answer.probabilities[team],
        escalation_level="CRITICAL" if urgent else "WARNING",
        request_id=decision.request_id,
    )
