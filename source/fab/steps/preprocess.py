##############################################################################
# (c) Crown copyright Met Office. All rights reserved.
# For further details please refer to the file COPYRIGHT
# which you should have received as part of this distribution
##############################################################################
"""
Fortran and C Preprocessing.

"""
import logging
import os
from pathlib import Path
from typing import List

from fab.constants import PRAGMAD_C
from fab.metrics import send_metric

from fab.steps.mp_exe import MpExeStep
from fab.util import log_or_dot_finish, input_to_output_fpath, log_or_dot, run_command, Timer, by_type
from fab.steps import check_for_errors
from fab.artefacts import ArtefactsGetter, SuffixFilter, CollectionGetter

logger = logging.getLogger(__name__)


class PreProcessor(MpExeStep):
    """
    Preprocess Fortran or C files with multiprocessing.

    """
    DEFAULT_SOURCE: ArtefactsGetter
    DEFAULT_OUTPUT_NAME: str
    DEFAULT_OUTPUT_SUFFIX: str
    LABEL: str

    def __init__(self,
                 source: ArtefactsGetter = None, output_collection=None, output_suffix=None,
                 preprocessor='cpp', common_flags: List[str] = None, path_flags: List = None,
                 name=None):
        """
        :param source:
            Defines the files to preprocess. Defaults to DEFAULT_SOURCE.
        :param output_collection:
            The name of the output artefact collection, defaulting to DEFAULT_OUTPUT_NAME.
        :param output_suffix:
            Defaults to DEFAULT_OUTPUT_SUFFIX.
        :param preprocessor:
            The name of the executable. Defaults to 'cpp'.
        :param common_flags:
            Used to construct a :class:`~fab.config.FlagsConfig' object.
        :param path_flags:
            Used to construct a :class:`~fab.config.FlagsConfig' object.
        :param name:
            Human friendly name for logger output, with sensible default.

        """
        super().__init__(exe=preprocessor, common_flags=common_flags, path_flags=path_flags, name=name or self.LABEL)

        self.source_getter = source or self.DEFAULT_SOURCE
        self.output_collection = output_collection or self.DEFAULT_OUTPUT_NAME
        self.output_suffix = output_suffix or self.DEFAULT_OUTPUT_SUFFIX

    def run(self, artefact_store, config):
        """
        Uses multiprocessing, unless disabled in the *config*.

        :param artefact_store:
            Contains artefacts created by previous Steps, and where we add our new artefacts.
            This is where the given :class:`~fab.artefacts.ArtefactsGetter` finds the artefacts to process.
        :param config:
            The :class:`fab.build_config.BuildConfig` object where we can read settings
            such as the project workspace folder or the multiprocessing flag.

        """
        super().run(artefact_store, config)

        files = list(self.source_getter(artefact_store))
        logger.info(f'preprocessing {len(files)} files')

        results = self.run_mp(items=files, func=self._process_artefact)
        check_for_errors(results, caller_label=self.name)

        log_or_dot_finish(logger)
        artefact_store[self.output_collection] = list(by_type(results, Path))

    def _process_artefact(self, fpath):
        """
        Expects an input file in the source folder.
        Writes the output file to the output folder, with a lower case extension.

        """
        output_fpath = input_to_output_fpath(config=self._config, input_path=fpath).with_suffix(self.output_suffix)

        # already preprocessed?
        if self._config.reuse_artefacts and output_fpath.exists():
            log_or_dot(logger, f'Preprocessor skipping: {fpath}')
        else:
            with Timer() as timer:
                output_fpath.parent.mkdir(parents=True, exist_ok=True)

                command = self.exe.split()
                command.extend(self.flags.flags_for_path(path=fpath, config=self._config))
                command.append(str(fpath))
                command.append(str(output_fpath))

                log_or_dot(logger, 'PreProcessor running command: ' + ' '.join(command))
                try:
                    run_command(command)
                except Exception as err:
                    raise Exception(f"error preprocessing {fpath}: {err}")

            send_metric(self.name, str(fpath), {'time_taken': timer.taken, 'start': timer.start})

        return output_fpath


def fortran_preprocessor(preprocessor=None, source=None,
                         output_collection='preprocessed_fortran', output_suffix='.f90',
                         name='preprocess fortran', **pp_kwds):
    """
    Return a step to preprocess Fortran files with multiprocessing.

    Params as per :class:`~fab.steps.preprocess.PreProcessor`.

    """
    # todo: we want to add -P ... IF it's not already there
    return PreProcessor(
        preprocessor=preprocessor or os.getenv('FPP', 'fpp -P'),
        source=source or SuffixFilter('all_source', '.F90'),
        output_collection=output_collection,
        output_suffix=output_suffix,
        name=name,
        **pp_kwds
    )


class DefaultCPreprocessorSource(ArtefactsGetter):
    """
    A source getter specifically for c preprocessing.
    Looks for the default output from pragma injection, falls back to default source finder.
    This allows the step to work with or without a preceding pragma step.

    """
    def __call__(self, artefact_store):
        return CollectionGetter(PRAGMAD_C)(artefact_store) \
               or SuffixFilter('all_source', '.c')(artefact_store)


DEFAULT_SOURCE_GETTER = DefaultCPreprocessorSource()


def c_preprocessor(preprocessor=None, source=None,
                   output_collection='preprocessed_c', output_suffix='.c',
                   name='preprocess c', **pp_kwds):
    """
    Return a step to preprocess C files with multiprocessing.

    Params as per :class:`~fab.steps.preprocess.PreProcessor`.

    """
    return PreProcessor(
        preprocessor=preprocessor or os.getenv('CPP', 'cpp -P'),
        source=source or DEFAULT_SOURCE_GETTER,
        output_collection=output_collection,
        output_suffix=output_suffix,
        name=name,
        **pp_kwds
    )
