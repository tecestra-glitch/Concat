"""Fronteira FX backend: FX terminal for BRL/USD/PYG across the Brazil–Paraguay border."""

__version__ = "0.1.0"


def main() -> None:
    """Console entrypoint: run the API with uvicorn."""
    import uvicorn

    uvicorn.run("fronteira_fx.main:app", host="0.0.0.0", port=8000)
