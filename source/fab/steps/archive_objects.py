##############################################################################
# (c) Crown copyright Met Office. All rights reserved.
# For further details please refer to the file COPYRIGHT
# which you should have received as part of this distribution
##############################################################################
"""
Object archive (.a) creation from a list of object files (.o) for use in static linking.

"""

import logging
from string import Template
from typing import List, Dict

from fab import artefacts
from fab.constants import BUILD_OUTPUT
from fab.steps import Step
from fab.util import CompiledFile, log_or_dot, run_command
from fab.artefacts import ArtefactsGetter

logger = logging.getLogger(__name__)

# DEFAULT_SOURCE_GETTER = artefacts.CompiledFortranAndC
DEFAULT_SOURCE_GETTER = "foo"
DEFAULT_COLLECTION_NAME = 'object archive'


class ArchiveObjects(Step):

    def __init__(self, source: ArtefactsGetter = None, archiver='ar',
                 output_fpath='$output/objects.a', output_collection=DEFAULT_COLLECTION_NAME, name='archive objects'):
        """
        Kwargs:
            - archiver: The archiver executable. Defaults to 'ar'.
            - output_fpath: The file path of the output archive file.

        """
        super().__init__(name)

        self.source_getter = source or DEFAULT_SOURCE_GETTER
        self.archiver = archiver
        self.output_fpath = output_fpath
        self.output_collection = output_collection

    def run(self, artefact_store: Dict, config):
        """
        Creates an object archive from the all the object files in the artefact store.

        By default, it finds the object files under the labels *compiled_c* and *compiled_fortran*.

        """
        super().run(artefact_store, config)

        output_fpath = Template(self.output_fpath).substitute(output=config.project_workspace / BUILD_OUTPUT)

        compiled_files: List[CompiledFile] = self.source_getter(artefact_store)

        command = [self.archiver]
        command.extend(['cr', output_fpath])
        command.extend(map(str, compiled_files))

        log_or_dot(logger, 'CreateObjectArchive running command: ' + ' '.join(command))
        try:
            run_command(command)
        except Exception as err:
            raise Exception(f"error creating object archive: {err}")

        artefact_store[self.output_collection] = [output_fpath]
