##############################################################################
# (c) Crown copyright Met Office. All rights reserved.
# For further details please refer to the file COPYRIGHT
# which you should have received as part of this distribution
##############################################################################
"""
Contains the :class:`~fab.build_config.BuildConfig` and helper classes.

"""
import getpass
import logging
import os
import sys
import warnings
from datetime import datetime
from fnmatch import fnmatch
from logging.handlers import RotatingFileHandler
from multiprocessing import cpu_count
from pathlib import Path
from string import Template
from typing import List, Optional, Iterable

from fab.artefacts import ArtefactSet, ArtefactStore
from fab.constants import BUILD_OUTPUT, SOURCE_ROOT, PREBUILD
from fab.metrics import send_metric, init_metrics, stop_metrics, metrics_summary
from fab.tools.category import Category
from fab.tools.tool_box import ToolBox
from fab.steps.cleanup_prebuilds import CLEANUP_COUNT, cleanup_prebuilds
from fab.util import TimerLogger, by_type, get_fab_workspace

logger = logging.getLogger(__name__)


class BuildConfig():
    """
    Contains and runs a list of build steps.

    The user is not expected to instantiate this class directly,
    but rather through the build_config() context manager.

    """
    def __init__(self, project_label: str,
                 tool_box: ToolBox,
                 multiprocessing: bool = True, n_procs: Optional[int] = None,
                 reuse_artefacts: bool = False,
                 fab_workspace: Optional[Path] = None, two_stage=False,
                 verbose=False):
        """
        :param project_label:
            Name of the build project. The project workspace folder is created from this name, with spaces replaced
            by underscores.
        :param tool_box: The ToolBox with all tools to use in the build.
        :param multiprocessing:
            An option to disable multiprocessing to aid debugging.
        :param n_procs:
            The number of cores to use for multiprocessing operations. Defaults to the number of available cores.
        :param reuse_artefacts:
            A flag to avoid reprocessing certain files on subsequent runs.
            WARNING: Currently unsophisticated, this flag should only be used by Fab developers.
            The logic behind flag will soon be improved, in a work package called "incremental build".
        :param fab_workspace:
            Overrides the FAB_WORKSPACE environment variable.
            If not set, and FAB_WORKSPACE is not set, the fab workspace defaults to *~/fab-workspace*.
        :param two_stage:
            Compile .mod files first in a separate pass. Theoretically faster in some projects..
        :param verbose:
            DEBUG level logging.

        """
        self._tool_box = tool_box
        self.two_stage = two_stage
        self.verbose = verbose
        compiler = tool_box[Category.FORTRAN_COMPILER]
        project_label = Template(project_label).safe_substitute(
            compiler=compiler.name,
            two_stage=f'{int(two_stage)+1}stage')

        self.project_label: str = project_label.replace(' ', '_')

        # workspace folder
        if not fab_workspace:
            fab_workspace = get_fab_workspace()
        logger.info(f"fab workspace is {fab_workspace}")

        self.project_workspace: Path = fab_workspace / self.project_label
        self.metrics_folder: Path = self.project_workspace / 'metrics' / self.project_label

        # source config
        self.source_root: Path = self.project_workspace / SOURCE_ROOT
        self.prebuild_folder: Path = self.build_output / PREBUILD

        # multiprocessing config
        self.multiprocessing = multiprocessing

        # turn off multiprocessing when debugging
        # todo: turn off multiprocessing when running tests, as a good test runner will run using mp
        if 'pydevd' in str(sys.gettrace()):
            logger.info('debugger detected, running without multiprocessing')
            self.multiprocessing = False

        self.n_procs = n_procs
        if self.multiprocessing and not self.n_procs:
            try:
                self.n_procs = max(1, len(os.sched_getaffinity(0)))
            except AttributeError:
                logger.error('could not enable multiprocessing')
                self.multiprocessing = False
                self.n_procs = None

        self.reuse_artefacts = reuse_artefacts

        # todo: should probably pull the artefact store out of the config
        # runtime
        self._artefact_store = ArtefactStore()

        self._build_timer = None
        self._start_time = None

    def __enter__(self):

        logger.info('')
        logger.info(f'initialising {self.project_label}')
        logger.info('')

        if self.verbose:
            logging.getLogger('fab').setLevel(logging.DEBUG)

        logger.info(f'building {self.project_label}')
        self._start_time = datetime.now().replace(microsecond=0)
        self._run_prep()

        with TimerLogger(f'running {self.project_label} build steps') as build_timer:
            # this will return to the build script
            self._build_timer = build_timer
            return self

    def __exit__(self, exc_type, exc_val, exc_tb):

        if not exc_type:  # None if there's no error.
            if CLEANUP_COUNT not in self.artefact_store:
                logger.info("no housekeeping step was run, using a default hard cleanup")
                cleanup_prebuilds(config=self, all_unused=True)

        logger.info(f"Building '{self.project_label}' took {datetime.now() - self._start_time}")

        # always
        self._finalise_metrics(self._start_time, self._build_timer)
        self._finalise_logging()

    @property
    def tool_box(self) -> ToolBox:
        ''':returns: the tool box to use.'''
        return self._tool_box

    @property
    def artefact_store(self) -> ArtefactStore:
        ''':returns: the Artefact instance for this configuration.
        '''
        return self._artefact_store

    @property
    def build_output(self) -> Path:
        ''':returns: the build output path.
        '''
        return self.project_workspace / BUILD_OUTPUT

    def add_current_prebuilds(self, artefacts: Iterable[Path]):
        """
        Mark the given file paths as being current prebuilds, not to be cleaned during housekeeping.

        """
        self.artefact_store[ArtefactSet.CURRENT_PREBUILDS].update(artefacts)

    def _run_prep(self):
        self._init_logging()

        logger.info('')
        logger.info(f'running {self.project_label}')
        logger.info('')

        self._prep_folders()

        init_metrics(metrics_folder=self.metrics_folder)

        # note: initialising here gives a new set of artefacts each run
        self.artefact_store.reset()

    def _prep_folders(self):
        self.source_root.mkdir(parents=True, exist_ok=True)
        self.build_output.mkdir(parents=True, exist_ok=True)
        self.prebuild_folder.mkdir(parents=True, exist_ok=True)

    def _init_logging(self):
        # add a file logger for our run
        self.project_workspace.mkdir(parents=True, exist_ok=True)
        log_file_handler = RotatingFileHandler(self.project_workspace / 'log.txt', backupCount=5, delay=True)
        log_file_handler.doRollover()
        logging.getLogger('fab').addHandler(log_file_handler)

        logger.info(f"{datetime.now()}")
        if self.multiprocessing:
            logger.info(f'machine cores: {cpu_count()}')
            logger.info(f'available cores: {len(os.sched_getaffinity(0))}')
            logger.info(f'using n_procs = {self.n_procs}')
        logger.info(f"workspace is {self.project_workspace}")

    def _finalise_logging(self):
        # remove our file logger
        fab_logger = logging.getLogger('fab')
        log_file_handlers = list(by_type(fab_logger.handlers, RotatingFileHandler))
        if len(log_file_handlers) != 1:
            warnings.warn(f'expected to find 1 RotatingFileHandler for removal, found {len(log_file_handlers)}')
        fab_logger.removeHandler(log_file_handlers[0])

    def _finalise_metrics(self, start_time, steps_timer):
        send_metric('run', 'label', self.project_label)
        send_metric('run', 'datetime', start_time.isoformat())
        send_metric('run', 'time taken', steps_timer.taken)
        send_metric('run', 'sysname', os.uname().sysname)
        send_metric('run', 'nodename', os.uname().nodename)
        send_metric('run', 'machine', os.uname().machine)
        send_metric('run', 'user', getpass.getuser())
        stop_metrics()
        metrics_summary(metrics_folder=self.metrics_folder)


# todo: better name? perhaps PathFlags?
class AddFlags():
    """
    Add command-line flags when our path filter matches.
    Generally used inside a :class:`~fab.build_config.FlagsConfig`.

    """
    def __init__(self, match: str, flags: List[str]):
        """
        :param match:
            The string to match against each file path.
        :param flags:
            The command-line flags to add for matching files.

        Both the *match* and *flags* arguments can make use of templating:

        - `$source` for *<project workspace>/source*
        - `$output` for *<project workspace>/build_output*
        - `$relative` for *<the source file's folder>*

        For example::

            # For source in the um folder, add an absolute include path
            AddFlags(match="$source/um/*", flags=['-I$source/include']),

            # For source in the um folder, add an include path relative to each source file.
            AddFlags(match="$source/um/*", flags=['-I$relative/include']),

        """
        self.match: str = match
        self.flags: List[str] = flags

    # todo: we don't need the project_workspace, we could just pass in the output folder
    def run(self, fpath: Path, input_flags: List[str], config):
        """
        Check if our filter matches a given file. If it does, add our flags.

        :param fpath:
            Filepath to check.
        :param input_flags:
            The list of command-line flags Fab is building for this file.
        :param config:
            Contains the folders for templating `$source` and `$output`.

        """
        params = {'relative': fpath.parent, 'source': config.source_root, 'output': config.build_output}

        # does the file path match our filter?
        if not self.match or fnmatch(str(fpath), Template(self.match).substitute(params)):
            # use templating to render any relative paths in our flags
            add_flags = [Template(flag).substitute(params) for flag in self.flags]

            # add our flags
            input_flags += add_flags

class ReplaceFlags(object):
    """
    Replace command-line flags with a new set when our path filter matches.
    Generally used inside a :class:`~fab.build_config.FlagsConfig`.

    """
    def __init__(self, match: str, flags: List[str]):
        """
        :param match:
            The string to match against each file path.
        :param flags:
            The command-line flags to add for matching files.

        Both the *match* and *flags* arguments can make use of templating:

        - `$source` for *<project workspace>/source*
        - `$output` for *<project workspace>/build_output*
        - `$relative` for *<the source file's folder>*

        For example::

            # For source in the um folder, add an absolute include path
            ReplaceFlags(match="$source/um/*", flags=['-I$source/include']),

            # For source in the um folder, add an include path relative to each source file.
            ReplaceFlags(match="$source/um/*", flags=['-I$relative/include']),

        """
        self.match: str = match
        self.flags: List[str] = flags

    # todo: we don't need the project_workspace, we could just pass in the output folder
    def run(self, fpath: Path, input_flags: List[str], config):
        """
        Check if our filter matches a given file. If it does, add our flags.

        :param fpath:
            Filepath to check.
        :param input_flags:
            The list of command-line flags Fab is building for this file.
        :param config:
            Contains the folders for templating `$source` and `$output`.

        """
        params = {'relative': fpath.parent, 'source': config.source_root, 'output': config.build_output}

        # does the file path match our filter?
        if not self.match or fnmatch(str(fpath), Template(self.match).substitute(params)):
            # use templating to render any relative paths in our flags
            new_flags = [Template(flag).substitute(params) for flag in self.flags]

            # add our flags
            input_flags == new_flags


class FlagsConfig():
    """
    Return command-line flags for a given path.

    Simply allows appending flags but may evolve to also replace and remove flags.

    """
    def __init__(self, common_flags: Optional[List[str]] = None, path_flags: Optional[List[AddFlags]] = None):
        """
        :param common_flags:
            List of flags to apply to all files. E.g `['-O2']`.
        :param path_flags:
            List of :class:`~fab.build_config.AddFlags` objects which apply flags to selected paths.

        """
        self.common_flags = common_flags or []
        self.path_flags = path_flags or []

    # todo: there's templating both in this method and the run method it calls.
    #       make sure it's all properly documented and rationalised.
    def flags_for_path(self, path: Path, config):
        """
        Get all the flags for a given file, in a reproducible order.

        :param path:
            The file path for which we want command-line flags.
        :param config:
            The config contains the source root and project workspace.

        """
        # We COULD make the user pass these template params to the constructor
        # but we have a design requirement to minimise the config burden on the user,
        # so we take care of it for them here instead.
        params = {'source': config.source_root, 'output': config.build_output}
        flags = [Template(i).substitute(params) for i in self.common_flags]

        for flags_modifier in self.path_flags:
            flags_modifier.run(path, flags, config=config)

        return flags
