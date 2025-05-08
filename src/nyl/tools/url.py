from urllib.parse import ParseResult, urlparse, urlunparse


def url_extract_basic_auth(
    url: str | ParseResult, mask: bool = False, strip_query: bool = False
) -> tuple[str, str | None, str | None]:
    """
    Extracts the username and password from a URL and returns a tuple of (url, username, password), where
    the returned url does not contain the username and password.

    If *mask* is enabled, the password is masked in the returned URL.
    """

    if isinstance(url, str):
        url = urlparse(url)

    username = url.username
    password = url.password
    if mask:
        netloc = f"{username}:{'***' if password else ''}@{url.hostname}"
        if url.port:
            netloc += f":{url.port}"
        url = url._replace(netloc=netloc)
    else:
        netloc = url.hostname or ""
        if url.port:
            netloc += f":{url.port}"
        url = url._replace(netloc=netloc)

    if strip_query:
        url = url._replace(query="")

    return urlunparse(url), username, password
