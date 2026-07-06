"""
Vercel Flask entrypoint.

Vercel's Python runtime scans common root entrypoint filenames (app.py, main.py, etc.).
This file maps that convention to the existing server package app factory.
"""

from server.app import create_app

app = create_app()

