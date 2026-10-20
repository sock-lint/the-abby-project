"""Keep Google authorization and homework proof material out of diagnostics."""
import re
from urllib.parse import urlsplit, urlunsplit


def scrub_google_oauth(event, hint=None):
    request = event.get("request") or {}
    parts = urlsplit(request.get("url", ""))
    path = parts.path.rstrip("/")
    is_google_authorization = path in {
        "/api/auth/google", "/api/auth/google/login", "/api/auth/google/callback", "/api/auth/google/exchange",
    }
    is_homework_submission = re.fullmatch(r"/api/homework/[0-9]+/submit", path) is not None
    if not (is_google_authorization or is_homework_submission):
        return event
    if is_google_authorization and event.get("type") == "transaction":
        return None
    # send_default_pii=False alone still permits exception locals and messages.
    # Preserve code coordinates, never authorization or submitted proof material.
    result = {key: event[key] for key in (
        "event_id", "timestamp", "level", "platform", "environment", "release", "dist", "type",
    ) if key in event}
    result["request"] = {"url": urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))}
    if is_homework_submission and event.get("type") == "transaction":
        # Retain duration and trace linkage without arbitrary span payloads.
        if "start_timestamp" in event:
            result["start_timestamp"] = event["start_timestamp"]
        result["transaction"] = "POST /api/homework/{id}/submit/"
        trace = (event.get("contexts") or {}).get("trace") or {}
        patterns = {
            "trace_id": r"[0-9a-fA-F]{32}",
            "span_id": r"[0-9a-fA-F]{16}",
            "parent_span_id": r"[0-9a-fA-F]{16}",
            "op": r"[A-Za-z0-9_.-]{1,64}",
            "status": r"[a-z_]{1,32}",
        }
        safe_trace = {key: trace[key] for key, pattern in patterns.items()
                      if isinstance(trace.get(key), str) and re.fullmatch(pattern, trace[key])}
        if safe_trace:
            result["contexts"] = {"trace": safe_trace}
    if "exception" in event:
        values = []
        for exc in event["exception"].get("values", []):
            frames = [{key: frame[key] for key in (
                "filename", "abs_path", "function", "module", "lineno", "in_app",
            ) if key in frame} for frame in exc.get("stacktrace", {}).get("frames", [])]
            values.append({"type": exc.get("type"), "module": exc.get("module"),
                           "stacktrace": {"frames": frames}})
        result["exception"] = {"values": values}
    return result
