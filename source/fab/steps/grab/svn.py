# ##############################################################################
#  (c) Crown copyright Met Office. All rights reserved.
#  For further details please refer to the file COPYRIGHT
#  which you should have received as part of this distribution
# ##############################################################################
from pathlib import Path
from typing import Optional, Union, Tuple
import xml.etree.ElementTree as ET

from fab.build_config import BuildConfig
from fab.steps import step
from fab.tools import run_command


def split_repo_url(url: str,
                   revision: Optional[str] = None) -> Tuple[str, Optional[str]]:
    """
    Separates revision from a repository URL.

    A default may be specified which will be used if none is found.

    :param url: Location of repository.
    :param revision: A default revision in case none is present.
    :return: URL and revision, the latter may be None.
    :raises: ValueError: If revision is present in the URL and disagrees with
                         the default specified.
    """
    # ToDo: This function is a bit mental. Is any of this necessary?
    url_revision = None
    at_split = url.split('@')
    if len(at_split) == 2:
        url_revision = at_split[1]
        if url_revision and revision and url_revision != revision:
            raise ValueError('Conflicting revisions in url and argument. Please provide as argument only.')
        url = at_split[0]
    else:
        assert len(at_split) == 1

    return url, revision or url_revision


def tool_available(command) -> bool:
    """Is the command line tool available?"""
    try:
        run_command([command, 'help'])
    except FileNotFoundError:
        return False
    return True


def _cli_revision_parts(revision):
    # return the command line argument to specif the revision, if there is one
    return ['--revision', str(revision)] if revision is not None else []


def is_working_copy(tool, dst: Union[str, Path]) -> bool:
    # is the given path is a working copy?
    try:
        run_command([tool, 'info'], cwd=dst)
    except RuntimeError:
        return False
    return True


def _svn_prep_common(config, src: str, dst_label: Optional[str], revision: Optional[str]) -> \
        Tuple[str, Path, Optional[str]]:
    src, revision = split_repo_url(src, revision)
    if not config.source_root.exists():
        config.source_root.mkdir(parents=True, exist_ok=True)
    dst: Path = config.source_root / (dst_label or '')

    return src, dst, revision


@step
def svn_export(config: BuildConfig, src: str, dst_label: Optional[str] = None, revision=None, tool='svn'):
    # todo: params in docstrings
    """
    Export an FCM repo folder to the project workspace.

    """
    src, dst, revision = _svn_prep_common(config, src, dst_label, revision)

    run_command([
        tool, 'export', '--force',
        *_cli_revision_parts(revision),
        src,
        str(dst)
    ])


@step
def svn_checkout(config, src: str, dst_label: Optional[str] = None, revision=None, tool='svn'):
    """
    Checkout or update an FCM repo.

    .. note::
        If the destination is a working copy, it will be updated to the given revision, **ignoring the source url**.
        As such, the revision should be provided via the argument, not as part of the url.

    """
    src, dst, revision = _svn_prep_common(config, src, dst_label, revision)

    # new folder?
    if not dst.exists():  # type: ignore
        run_command([
            tool, 'checkout',
            *_cli_revision_parts(revision),
            src, str(dst)
        ])

    else:
        # working copy?
        if is_working_copy(tool, dst):  # type: ignore
            # update
            # todo: ensure the existing checkout is from self.src?
            run_command([tool, 'update', *_cli_revision_parts(revision)], cwd=dst)  # type: ignore
        else:
            # we can't deal with an existing folder that isn't a working copy
            raise ValueError(f"destination exists but is not an fcm working copy: '{dst}'")


def svn_merge(config, src: str, dst_label: Optional[str] = None, revision=None, tool='svn'):
    """
    Merge an FCM repo into a local working copy.

    """
    src, dst, revision = _svn_prep_common(config, src, dst_label, revision)

    if not dst or not is_working_copy(tool, dst):
        raise ValueError(f"destination is not a working copy: '{dst}'")

    # We seem to need the url and version combined for this operation.
    # The help for fcm merge says it accepts the --revision param, like other commands,
    # but it doesn't seem to be recognised.
    rev_url = f'{src}'
    if revision is not None:
        rev_url += f'@{revision}'

    run_command([tool, 'merge', '--non-interactive', rev_url], cwd=dst)
    check_conflict(tool, dst)


def check_conflict(tool, dst):
    # check if there's a conflict
    xml_str = run_command([tool, 'status', '--xml'], cwd=dst)
    root = ET.fromstring(xml_str)

    for target in root:
        if target.tag != 'target':
            continue
        for entry in target:
            if entry.tag != 'entry':
                continue
            for element in entry:
                if element.tag == 'wc-status' and element.attrib['item'] == 'conflicted':
                    raise RuntimeError(f'{tool} merge encountered a conflict:\n{xml_str}')
    return False
