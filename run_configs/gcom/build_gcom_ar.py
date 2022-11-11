#!/usr/bin/env python3
##############################################################################
# (c) Crown copyright Met Office. All rights reserved.
# For further details please refer to the file COPYRIGHT
# which you should have received as part of this distribution
##############################################################################
import os

from fab.build_config import BuildConfig
from fab.steps.archive_objects import ArchiveObjects
from fab.util import get_tool

from gcom_build_steps import common_build_steps, parse_args
from grab_gcom import gcom_grab_config


def gcom_ar_config(revision=None, compiler=None):
    """
    Create an object archive for linking.

    """
    # We want a separate project folder for each compiler. Find out which compiler we'll be using.
    compiler, _ = get_tool(os.getenv('FC'))

    config = BuildConfig(
        project_label=f'gcom object archive {revision} {compiler}',
        source_root=gcom_grab_config(revision=revision).source_root,
        steps=[
            *common_build_steps(fortran_compiler=compiler),
            ArchiveObjects(output_fpath='$output/libgcom.a'),
        ]
    )

    return config


if __name__ == '__main__':
    args = parse_args()
    gcom_ar_config(revision=args.revision, compiler=args.compiler).run()
