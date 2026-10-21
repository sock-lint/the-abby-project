"""Typed authoring failures shared by native services and transports."""
from .loader import ContentPackError


class ContentAuthorPermissionDenied(ContentPackError):
    """The current actor cannot author or modify the selected content."""


class ContentObjectNotFound(ContentPackError):
    """The selected content is missing or outside the author's scope."""
