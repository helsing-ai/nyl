"""
Swiss-army-knife for various common operations in conjunction with Nyl (Kubernetes, secrets management, etc).
"""

from nyl.tools.typer import new_typer


app = new_typer(name="tools", help=__doc__)

from . import sops  # noqa: E402
from . import bcrypt  # noqa: F401,E402

app.add_typer(sops.app)
