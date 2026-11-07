"""Backward-compatible ASGI name for the single Foundation application."""

from cqa.backend.main import app, create_app

__all__ = ["app", "create_app"]
