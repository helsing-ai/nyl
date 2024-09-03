from kraken.common import buildscript
buildscript(requirements=["kraken-build @ git+https://github.com/kraken-build/kraken.git@nr/python-project#egg=kraken-build&subdirectory=kraken-build"])

from kraken.build.python.v1alpha1 import python_project
python_project()
