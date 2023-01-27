# ##############################################################################
#  (c) Crown copyright Met Office. All rights reserved.
#  For further details please refer to the file COPYRIGHT
#  which you should have received as part of this distribution
# ##############################################################################
from pathlib import Path
from typing import Dict

from fab.steps.grab.fcm import GrabFcmBase
from fab.tools import run_command


class FcmExport(GrabFcmBase):
    """
    Export an FCM repo folder to the project workspace.

    """
    def run(self, artefact_store: Dict, config):
        super().run(artefact_store, config)

        dst: Path = config.source_root / self.dst_label

        run_command([
            'fcm', 'export', '--force',
            *self._cli_revision_parts(),
            self.src,
            str(dst)
        ])