# ##############################################################################
#  (c) Crown copyright Met Office. All rights reserved.
#  For further details please refer to the file COPYRIGHT
#  which you should have received as part of this distribution
# ##############################################################################
from pathlib import Path
from typing import Dict

from fab.steps.grab.fcm import is_working_copy, GrabFcmBase
from fab.tools import run_command


class FcmCheckout(GrabFcmBase):
    """
    Checkout or update an FCM repo.

    .. note::
        If the destination is a working copy, it will be updated to the given revision, **ignoring the source url**.
        As such, the revision should be provided via the argument, not as part of the url.

    """
    def run(self, artefact_store: Dict, config):
        super().run(artefact_store, config)

        dst: Path = config.source_root / self.dst_label

        # new folder?
        if not dst.exists():
            run_command([
                'fcm', 'checkout',
                *self._cli_revision_parts(),
                self.src, str(dst)
            ])

        else:
            # working copy?
            if is_working_copy(dst):
                # update
                # todo: ensure the existing checkout is from self.src?
                run_command(['fcm', 'update', *self._cli_revision_parts()], cwd=dst)
            else:
                # we can't deal with an existing folder that isn't a working copy
                raise ValueError(f"destination exists but is not an fcm working copy: '{dst}'")