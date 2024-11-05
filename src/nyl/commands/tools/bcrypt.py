import sys
from typing import Optional

from bcrypt import gensalt, hashpw

from . import app


@app.command()
def bcrypt(text: Optional[str] = None) -> None:
    """
    Bcrypt-hash the specified text. If no argument is specified, read from stdin.
    """

    if text is None:
        text = sys.stdin.read()

    print(hashpw(text.encode("utf-8"), gensalt()).decode("utf-8"))
