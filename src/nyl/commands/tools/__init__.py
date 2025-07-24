"""
Swiss-army-knife for various common operations in conjunction with Nyl (Kubernetes, secrets management, etc).
"""

from typer import Typer

from nyl.tools.typer import new_typer

app: Typer = new_typer(name="tools", help=__doc__)

from . import (  # noqa: E402,F401
    bcrypt,
    sops,
)

app.add_typer(sops.app)
