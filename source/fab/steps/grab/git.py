# ##############################################################################
#  (c) Crown copyright Met Office. All rights reserved.
#  For further details please refer to the file COPYRIGHT
#  which you should have received as part of this distribution
# ##############################################################################
from abc import ABC
from pathlib import Path
from typing import Union, Dict, Tuple
import xml.etree.ElementTree as ET

from fab.steps.grab import GrabSourceBase
from fab.tools import run_command


def tool_available() -> bool:
    """Is the command line git tool available?"""
    try:
        run_command(['git', 'help'])
    except FileNotFoundError:
        return False
    return True


def get_remotes() -> Dict[str, str]:
    """Get the remotes as a mapping from label to url."""
    output = run_command(['git', 'remote', '-v'])
    lines = output.split('\n')
    remotes = {}
    for line in lines:
        if line:
            split = line.split()
            remotes[split[0]] = split[1]
    return remotes


def _next_name(base, current_names, i=1):
    """Return the next name in the sequence <base><n>."""
    while True:
        next = f'{base}{i}'
        if next not in current_names:
            return next
        i += 1


class GrabGitBase(GrabSourceBase, ABC):
    """
    Base class for Git operations.

    """
    def __init__(self, src: Union[str, Path], dst: str, revision=None, name=None):
        """
        :param src:
            Such as `https://github.com/metomi/fab-test-data.git` or path to a local working copy.
        :param dst:
            The name of a sub folder, in the project workspace, in which to put the source.
            If not specified, the code is copied into the root of the source folder.
        :param revision:
            E.g 'vn6.3'.
        :param name:
            Human friendly name for logger output, with sensible default.

        """
        super().__init__(src, dst, name=name, revision=revision)

    def run(self, artefact_store: Dict, config):
        if not tool_available():
            raise RuntimeError("git command line tool not available")
        super().run(artefact_store, config)

    def is_working_copy(self, dst: Union[str, Path]) -> bool:
        """Is the given path is a working copy?"""
        try:
            run_command(['git', 'status'], cwd=dst)
        except RuntimeError:
            return False
        return True

    def fetch(self) -> str:
        """
        Fetch the source url, adding a new remote if necessary.

        Returns the remote alias.

        """
        # todo: check it's a url not a path?
        remotes = get_remotes()
        if self.src not in remotes.values():
            remote_name = self.add_remote()
        else:
            remote_name = [k for k, v in remotes.items() if v == self.src][0]

        # ok it's a remote, we can fetch
        command = ['git', 'fetch', '--depth', '1', remote_name]
        if self.revision:
            command.append(self.revision)

        run_command(command)
        return remote_name

    def add_remote(self) -> str:
        """
        Add a new remote with the name `remote<n>`

        Returns the remote alias.

        """
        # todo: check it's a url not a path?
        remotes = get_remotes()
        remote_name = _next_name(base='remote', current_names=remotes.keys())
        run_command(['git', 'remote', 'add', remote_name, self.src])
        return remote_name


# todo: allow cli args, e.g to set the depth
class GitCheckout(GrabGitBase):
    """
    Checkout or update a Git repo.

    If a revision is provided, no history is fetched.

    """
    def run(self, artefact_store: Dict, config):
        super().run(artefact_store, config)

        # new folder?
        if not self._dst.exists():  # type: ignore
            revision_parts = ['--branch', str(self.revision)] if self.revision is not None else []
            run_command([
                'git', 'clone',
                '--depth', '1',
                *revision_parts,
                self.src, str(self._dst)
            ])

        else:
            if self.is_working_copy(self._dst):  # type: ignore
                remote_name = self.fetch()
                command = [
                    'git', 'checkout',
                    '--detach',
                    remote_name,
                ]
                if self.revision:
                    command.append(str(self.revision))

                run_command(command, cwd=self._dst)
            else:
                # we can't deal with an existing folder that isn't a working copy
                raise ValueError(f"destination exists but is not an fcm working copy: '{self._dst}'")


class GitMerge(GrabGitBase):
    """
    Merge a git repo into a local working copy.

    """
    def run(self, artefact_store: Dict, config):
        super().run(artefact_store, config)
        if not self._dst or not self.is_working_copy(self._dst):
            raise ValueError(f"destination is not a working copy: '{self._dst}'")

        # we need to make sure the src is in the list of remotes

        run_command(['git', 'merge', self.revision], cwd=self._dst)
        self.check_conflict()

    def check_conflict(self):
        # check if there's a conflict
        xml_str = run_command([self.command, 'status', '--xml'], cwd=self._dst)
        root = ET.fromstring(xml_str)

        for target in root:
            if target.tag != 'target':
                continue
            for entry in target:
                if entry.tag != 'entry':
                    continue
                for element in entry:
                    if element.tag == 'wc-status' and element.attrib['item'] == 'conflicted':
                        raise RuntimeError(f'{self.command} merge encountered a conflict:\n{xml_str}')
        return False
