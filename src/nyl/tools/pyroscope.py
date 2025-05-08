import os


def init_pyroscope() -> None:
    if not (pyroscope_url := os.getenv("NYL_PYROSCOPE_URL")):
        return

    import posixpath
    import threading
    import time
    import requests
    from urllib.parse import parse_qs, urlparse, urlunparse
    from loguru import logger
    from nyl import __version__

    parsed = urlparse(pyroscope_url)

    params = parse_qs(parsed.query)
    server_address = urlunparse(parsed._replace(netloc=parsed.hostname, query=None))  # type: ignore # TODO
    logger.opt(colors=True).info("Enabling Pyroscope profiling with destination <yellow>{}</>", server_address)

    from pyroscope import configure  # type: ignore

    # Periodically check if pyroscope server is available.
    def check_pyroscope_server() -> None:
        while True:
            try:
                ready_url = urlunparse(parsed._replace(query=None, path=posixpath.join(parsed.path, "ready")))  # type: ignore # TODO
                requests.get(ready_url)
            except requests.RequestException as e:
                logger.warning("Pyroscope server is not ready: {}", e)
            except Exception as e:
                logger.warning("Unexpected exception while checking pyroscope server: {}", e)
            time.sleep(30)

    threading.Thread(target=check_pyroscope_server, daemon=True).start()

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
