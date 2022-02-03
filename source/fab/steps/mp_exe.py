"""
A step for running multiple files through a command line tool using multiprocessing.

"""
from typing import Dict, List

from fab.config import FlagsConfig, AddFlags
from fab.steps import Step


# Initial motivation: unify constructors for preprocessors and compilers as they were already diverging.
class MpExeStep(Step):
    """
    Base class which handles the common and per-file flag config.

    """
    def __init__(self, exe, common_flags: List[str], path_flags: List[AddFlags], name):
        super().__init__(name)
        self.exe = exe
        self._flags = FlagsConfig(workspace=self.workspace, common_flags=common_flags, path_flags=path_flags)

    # todo: can we do more up in this superclass?
    def run(self, artefacts: Dict):
        raise NotImplementedError