

API_BASE = "http://127.0.0.1:8001"  # مثال

TOKEN: str | None = None
ROLE: str | None = None
USERNAME: str | None = None

# UI hook: يناديه api.py لما يصير 401
ON_UNAUTHORIZED = None  # type: ignore
