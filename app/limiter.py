"""Shared rate limiter instance (per-process; Redis-backed for multi-worker prod)."""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
