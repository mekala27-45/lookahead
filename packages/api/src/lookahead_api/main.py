"""ASGI entry point: `uvicorn lookahead_api.main:app`."""

from lookahead_api.app import create_app

app = create_app()
