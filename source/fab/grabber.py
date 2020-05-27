##############################################################################
# (c) Crown copyright Met Office. All rights reserved.
# For further details please refer to the file COPYRIGHT
# which you should have received as part of this distribution
##############################################################################
"""
Core of the source extraction tool.
"""
import logging
from pathlib import Path
from typing import Sequence


def entry() -> None:
    """
    Extract and merge up a source tree from several repositories.
    """
    import argparse
    import sys
    import fab

    logger = logging.getLogger('fab-grab')
    logger.addHandler(logging.StreamHandler(sys.stderr))

    description = "Build a source tree from extracted source."
    parser = argparse.ArgumentParser(add_help=False,
                                     description=description)
    parser.add_argument('-h', '-help', '--help', action='help',
                        help="Print this help and exit.")
    parser.add_argument('-V', '--version', action='version',
                        version=fab.__version__,
                        help="Print version identifier and exit.")
    parser.add_argument('-v', '--verbose', action='store_true',
                        help="Produce a running commentary on progress.")
    parser.add_argument('-w', '--workspace', metavar='PATH', type=Path,
                        default=Path.cwd() / 'working',
                        help="Directory for working files.")
    parser.add_argument('repositories', nargs='+', metavar='URL',
                        help="Location from which to extract source.")

    arguments = parser.parse_args()

    if arguments.verbose:
        logger.setLevel(logging.INFO)
    else:
        logger.setLevel(logging.WARNING)

        application = fab.grabber.Grab(arguments.workspace)
        application.run(arguments.repositories)


class Grab(object):
    def __init__(self, workspace: Path):
        self._workspace = workspace

    def run(self, repositories: Sequence[str]) -> None:
        pass
