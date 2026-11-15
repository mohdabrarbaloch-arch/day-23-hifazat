"""Vercel serverless entry — imports the full app.

The sandbox builds this file in isolation, so it must import the real app
package rather than re-implementing it.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Production settings (read from Vercel env vars).
os.environ.setdefault("DEBUG", "false")

from app.main import app  # noqa: E402

handler = app
