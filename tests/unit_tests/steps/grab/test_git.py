##############################################################################
# (c) Crown copyright Met Office. All rights reserved.
# For further details please refer to the file COPYRIGHT
# which you should have received as part of this distribution
##############################################################################
from distutils.spawn import find_executable
from pathlib import Path
import shutil
from signal import SIGTERM
from subprocess import Popen, run
from typing import List

from pytest import TempPathFactory, fixture, mark, raises

from fab import FabException
from fab.build_config import BuildConfig
from fab.steps.grab.git import git_checkout

from .support import Workspace, file_tree_compare


class TestGit:
    """
    Tests of the Git repository interface.
    """
    @fixture(scope='class')
    def workspace(self, tmp_path_factory: TempPathFactory) -> Workspace:
        """
        Set up a repository and return its path along with the path of the
        original file tree.
        """
        tree_path = tmp_path_factory.mktemp('tree', numbered=True)
        (tree_path / 'alpha').write_text("First file")
        (tree_path / 'beta').mkdir()
        (tree_path / 'beta' / 'gamma').write_text("Second file")

        repo_path = tmp_path_factory.mktemp('repo', numbered=True)
        command = ['git', 'init', str(repo_path)]
        assert run(command).returncode == 0
        #
        # We have to configure this information or the forthcoming commands
        # will fail.
        #
        command = ['git', 'config', 'user.name', 'Testing Tester Tests']
        assert run(command, cwd=str(repo_path)).returncode == 0
        command = ['git', 'config', 'user.email', 'tester@example.com']
        assert run(command, cwd=str(repo_path)).returncode == 0

        for file_object in tree_path.glob('*'):
            if file_object.is_dir():
                shutil.copytree(str(file_object),
                                str(repo_path / file_object.name))
            else:
                shutil.copy(str(file_object),
                            str(repo_path / file_object.name))
        command = ['git', 'add', '-A']
        assert run(command, cwd=str(repo_path)).returncode == 0
        command = ['git', 'commit', '-m', "Initial import"]
        assert run(command, cwd=str(repo_path)).returncode == 0
        return Workspace(repo_path.absolute(), tree_path.absolute())

    def test_checkout_from_file(self, workspace: Workspace, tmp_path: Path):
        """
        Tests that a source tree can be extracted from a local repository.
        """
        config = BuildConfig(fab_workspace=tmp_path, project_label='foo')
        parent_url = f'file://{workspace.repo_path}'
        git_checkout(config, parent_url)
        assert (tmp_path / 'foo' / 'source' / '.git').exists()
        file_tree_compare(workspace.tree_path, tmp_path / 'foo' / 'source')

    def test_missing_repo(self, tmp_path: Path):
        """
        Tests that an error is returned if the repository is not there.
        """
        config = BuildConfig(fab_workspace=tmp_path, project_label='bar')
        parent_url = f'file://{tmp_path}/nosuch.repo'
        with raises(FabException):
            git_checkout(config, parent_url)

    @mark.skipif(not find_executable('git-daemon'),
                 reason="Unable to find git daemon")
    def test_extract_from_git(self, workspace, tmp_path: Path):
        """
        Checks that a source tree can be extracted from a Git repository
        accessed through its own protocol.
        """
        command: List[str] = ['git', 'daemon', '--reuseaddr',
                              '--base-path=' + str(workspace.repo_path.parent),
                              str(workspace.repo_path)]
        process = Popen(command)

        config = BuildConfig('baz', fab_workspace=tmp_path)
        parent_url = 'git://localhost/' + workspace.repo_path.name
        git_checkout(config, parent_url)
        assert (tmp_path / 'baz' / 'source' / '.git').exists()
        file_tree_compare(workspace.tree_path, tmp_path / 'baz' / 'source')

        process.send_signal(SIGTERM)
        process.wait(timeout=2)
        assert process.returncode == -15

    @mark.skip(reason="Too hard to test at the moment.")
    def test_extract_from_http(self, workspace, tmp_path: Path):
        """
        Checks that a source tree can be extracted from a Git repository
        accessed through HTTP.

        TODO: This is hard to test without a full Apache installation. For the
              moment we forgo the test on the basis that it's too hard.
        """
        pass
