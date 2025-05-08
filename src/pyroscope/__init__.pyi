from typing import ContextManager

def configure(
    application_name: str,
    server_address: str,
    tags: dict[str, str] | None = None,
    basic_auth_username: str = "",
    basic_auth_password: str = "",
    tenant_id: str = "",
) -> None: ...
def tag_wrapper(tags: dict[str, str]) -> ContextManager[None]: ...
