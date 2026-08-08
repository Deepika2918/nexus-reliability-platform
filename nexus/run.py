"""One-command startup: platform server."""

import uvicorn

from nexus.config import settings


def main() -> None:
    uvicorn.run(
        "nexus.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
