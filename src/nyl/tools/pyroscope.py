import os
from urllib.parse import parse_qs, urlparse, urlunparse
from loguru import logger
from nyl import __version__


def init_pyroscope() -> None:
    if not (pyroscope_url := os.getenv("NYL_PYROSCOPE_URL")):
        return

    parsed = urlparse(pyroscope_url)

    params = parse_qs(parsed.query)
    server_address = urlunparse(parsed._replace(netloc=parsed.hostname, query=None))  # type: ignore # TODO
    logger.opt(colors=True).info("Enabling Pyroscope profiling with destination <yellow>{}</>", server_address)

    from pyroscope import configure  # type: ignore

    application_name = params.pop("application_name", ["nyl"])[0]
    application_name = os.getenv("NYL_PYROSCOPE_APPLICATION_NAME", application_name)

    tenant_id = params.pop("tenant_id", [""])[0]
    tenant_id = os.getenv("NYL_PYROSCOPE_TENANT_ID", tenant_id)

    configure(
        server_address=server_address,
        application_name=application_name,
        tenant_id=tenant_id,
        tags={"version": __version__, **{k: v[0] for k, v in params.items()}},
        basic_auth_username=parsed.username or "",
        basic_auth_password=parsed.password or "",
    )
