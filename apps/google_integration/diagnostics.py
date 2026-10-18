"""Bounded Calendar error metadata; never export provider messages or content."""
import json
import re
from urllib.parse import urlsplit

from googleapiclient.errors import HttpError


# Google documents these distinct Calendar 403 reasons and their domains:
# https://developers.google.com/workspace/calendar/api/guides/errors
_FORBIDDEN_REASONS = {
    "userRateLimitExceeded": "usageLimits",
    "rateLimitExceeded": "usageLimits",
    "quotaExceeded": "usageLimits",
    "forbiddenForNonOrganizer": "calendar",
}
_MAX_CONTENT_BYTES = 16 * 1024


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Ambiguous provider response")
        result[key] = value
    return result


def _calendar_uri(uri, operation):
    if (not isinstance(uri, str) or len(uri) > 4096 or
            any(ord(char) <= 32 for char in uri)):
        return False
    try:
        parsed = urlsplit(uri)
    except ValueError:
        return False
    path = r"/calendar/v3/calendars/[^/]+/events"
    if operation == "update":
        path += r"/[^/]+"
    return (parsed.scheme == "https" and parsed.netloc == "www.googleapis.com" and
            not parsed.fragment and re.fullmatch(path, parsed.path) is not None)


def calendar_failure_diagnostics(error, *, operation):
    """Return fixed labels for a direct Calendar call's failure, or unknown.

    The caller must pass None for failures after the Google call (for example,
    saving its local mapping). Exception causes, free-form ``HttpError.reason``
    and arbitrary ErrorInfo objects cannot supply these labels.
    """
    operation = operation if operation in {"insert", "update"} else "unknown"
    result = {"operation": operation, "status": None, "reason": "unknown"}
    if (operation == "unknown" or type(error) is not HttpError or
            not _calendar_uri(error.uri, operation)):
        return result
    status = getattr(error.resp, "status", None)
    if type(status) is not int or not 100 <= status <= 599:
        return result
    result["status"] = status
    content = error.content
    if status != 403 or not isinstance(content, bytes) or len(content) > _MAX_CONTENT_BYTES:
        return result
    try:
        payload = json.loads(content.decode("utf-8"), object_pairs_hook=_unique_object)
    except (ValueError, UnicodeError, RecursionError):
        return result
    if not isinstance(payload, dict) or not isinstance(payload.get("error"), dict):
        return result
    details = payload["error"]
    if type(details.get("code")) is not int or details["code"] != status:
        return result
    errors = details.get("errors")
    if not isinstance(errors, list) or not 1 <= len(errors) <= 4:
        return result
    reasons = set()
    for item in errors:
        if not isinstance(item, dict) or not isinstance(item.get("reason"), str):
            return result
        reason = item["reason"]
        if reason not in _FORBIDDEN_REASONS or item.get("domain") != _FORBIDDEN_REASONS[reason]:
            return result
        reasons.add(reason)
    if len(reasons) == 1:
        result["reason"] = reasons.pop()
    return result
