"""Keep temporary Google authorization material out of error/trace envelopes."""
from urllib.parse import urlsplit, urlunsplit


def scrub_google_oauth(event, hint=None):
    request = event.get("request") or {}
    parts = urlsplit(request.get("url", ""))
    if parts.path.rstrip("/") not in {
        "/api/auth/google", "/api/auth/google/login", "/api/auth/google/callback", "/api/auth/google/exchange",
    }:
        return event
    if event.get("type") == "transaction":
        return None
    # send_default_pii=False alone still permits exception locals and messages.
    # Preserve code coordinates, never provider responses or decrypted locals.
    result = {key: event[key] for key in (
        "event_id", "timestamp", "level", "platform", "environment", "release", "dist", "type",
    ) if key in event}
    result["request"] = {"url": urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))}
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
