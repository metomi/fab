"""
Object archive (.a) creation from a list of object files (.o) for use in static linking.

"""

import logging
from typing import List, Dict

from fab.steps import Step
from fab.util import CompiledFile, log_or_dot, run_command, Artefacts, SourceGetter

logger = logging.getLogger('fab')


DEFAULT_SOURCE_GETTER = Artefacts(['compiled_c', 'compiled_fortran'])


class ArchiveObjcts(Step):

    def __init__(self, source: SourceGetter=None, archiver='ar', output_fpath='output.a', name='archive objects'):
        """
        Kwargs:
            - archiver: The archiver executable. Defaults to 'ar'.
            - output_fpath: The file path of the output archive file.

        """
        super().__init__(name)
        self.source_getter = source or DEFAULT_SOURCE_GETTER
        self.archiver = archiver
        self.output_fpath = output_fpath

    def run(self, artefacts: Dict, config):
        """
        Creates an archive object from the *compiled_files* artefact.

        (Current thinking) does not create an entry in the artefacts dict because the config which creates this step
        is responsible for managing which files are passed to the linker.

        """
        super().run(artefacts, config)

        compiled_files: List[CompiledFile] = self.source_getter(artefacts)

        command = [self.archiver]
        command.extend(['cr', self.output_fpath])
        command.extend([str(a.output_fpath) for a in compiled_files])

        log_or_dot(logger, 'CreateObjectArchive running command: ' + ' '.join(command))
        try:
            run_command(command)
        except Exception as err:
            raise Exception(f"error creating object archive: {err}")

        return self.output_fpath
