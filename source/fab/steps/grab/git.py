# ##############################################################################
#  (c) Crown copyright Met Office. All rights reserved.
#  For further details please refer to the file COPYRIGHT
#  which you should have received as part of this distribution
# ##############################################################################
import warnings
from pathlib import Path
from typing import Optional, Union

from fab import FabException
from fab.build_config import BuildConfig
from fab.steps import step
from fab.tools import run_command


def __current_commit(folder=None):
    folder = folder or '.'
    output = run_command(['git', 'log', '--oneline', '-n', '1'], cwd=folder)
    commit = output.split()[0]
    return commit


def tool_available() -> bool:
    """Is the command line git tool available?"""
    try:
        run_command(['git', 'help'])
    except FileNotFoundError:
        return False
    return True


def __is_working_copy(dst: Union[str, Path]) -> bool:
    """Is the given path is a working copy?"""
    try:
        run_command(['git', 'status'], cwd=dst)
    except RuntimeError:
        return False
    return True


# todo: allow shallow fetch with --depth 1
def __fetch(src: str, dst: Path, revision: Optional[str] = None) -> None:
    """
    Downloads changes from a repository into another.

    :param src: Repository to fetch from.
    :param dst: Repository to fetch to.
    :param revision: ID if revision to fetch.
    """
    command = ['git', 'fetch', src]
    if revision:
        command.append(revision)

    run_command(command, cwd=str(dst))


# todo: allow cli args, e.g to set the depth
@step
def git_checkout(config: BuildConfig,
                 src: str,
                 dst_label: str = '',
                 revision: Optional[str] = None) -> None:
    """
    Checkout or update a Git repository.

    :param config: Fab context object.
    :param src: Repository to refer to.
    :param dst_label: Directory to use at destination.
    :param revision: ID of revision to checkout.
    """
    _dst = config.source_root / dst_label

    # create folder?
    if not _dst.exists():
        _dst.mkdir(parents=True)
        run_command(['git', 'init', '.'], cwd=_dst)

    elif not __is_working_copy(_dst):  # type: ignore
        raise ValueError(f"destination exists but is not a working copy: '{_dst}'")

    try:
        __fetch(src, _dst, revision)
    except RuntimeError as ex:
        message = f"Unable to fetch from repository '{src}'"
        raise FabException(message) from ex
    run_command(['git', 'checkout', 'FETCH_HEAD'], cwd=_dst)

    try:
        _dst.relative_to(config.project_workspace)
        run_command(['git', 'clean', '-f'], cwd=_dst)
    except ValueError:
        warnings.warn(f'not safe to clean git source in {_dst}')


@step
def git_merge(config, src: str, dst_label: str = '', revision=None):
    """
    Merge a git repo into a local working copy.

    """
    _dst = config.source_root / dst_label

    if not _dst or not __is_working_copy(_dst):
        raise ValueError(f"destination is not a working copy: '{_dst}'")

    __fetch(src=src, dst=_dst, revision=revision)

    try:
        run_command(['git', 'merge', 'FETCH_HEAD'], cwd=_dst)
    except RuntimeError as err:
        run_command(['git', 'merge', '--abort'], cwd=_dst)
        raise RuntimeError(f"Error merging {revision}. Merge aborted.\n{err}")
