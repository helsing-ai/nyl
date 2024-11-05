import yaml

from nyl.resources.applyset import ApplySet
from nyl.resources.placeholder import Placeholder

from . import app


@app.command()
def crds() -> None:
    """
    Print out the CRDs that need to be installed on a Kubernetes cluster before you can use all of Nyl's features.
    """

    print("---")
    print(yaml.safe_dump(ApplySet.CRD))
    print("---")
    print(yaml.safe_dump(Placeholder.CRD))
