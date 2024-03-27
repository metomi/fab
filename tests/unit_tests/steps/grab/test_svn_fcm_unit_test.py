# ##############################################################################
#  (c) Crown copyright Met Office. All rights reserved.
#  For further details please refer to the file COPYRIGHT
#  which you should have received as part of this distribution
# ##############################################################################
from pathlib import Path
from subprocess import Popen, run
import time
from typing import List, Tuple

from pytest import fixture, mark, raises

from fab import FabException
from fab.build_config import BuildConfig
from fab.steps.grab.svn import split_repo_url, svn_export

from .support import Workspace, file_tree_compare


class TestRevision(object):
    # test the handling of the revision in the base class

    def test_no_revision(self):
        assert split_repo_url(url='url') == ('url', None)

    def test_url_revision(self):
        assert split_repo_url(url='url@rev') == ('url', 'rev')

    def test_revision_param(self):
        assert split_repo_url(url='url', revision='rev') == ('url', 'rev')

    def test_both_matching(self):
        assert split_repo_url(url='url@rev', revision='rev') == ('url', 'rev')

    def test_both_different(self):
        with raises(ValueError):
            assert split_repo_url(url='url@rev', revision='bev')


class TestSubversion:
    """
    Tests of the Subversion repository interface.
    """
    @fixture(scope='class')
    def workspace(self, tmp_path_factory) -> Workspace:
        """
        Set up a repository and return its path along with the path of the
        original file tree.
        """
        repo_path = tmp_path_factory.mktemp('repo', numbered=True)
        command = ['svnadmin', 'create', str(repo_path)]
        assert run(command).returncode == 0
        tree_path = tmp_path_factory.mktemp('tree', numbered=True)
        (tree_path / 'alpha').write_text("First file")
        (tree_path / 'beta').mkdir()
        (tree_path / 'beta' / 'gamma').write_text("Second file")
        command = ['svn', 'import', '-m', "Initial import",
                   str(tree_path), f'file://{repo_path}/trunk']
        assert run(command).returncode == 0
        return Workspace(repo_path, tree_path)

    def test_extract_from_file(self, workspace, tmp_path: Path) -> None:
        """
        Checks that a source tree can be extracted from a Subversion
        repository stored on disc.
        """
        source_path = tmp_path / 'foo' / 'source'
        config = BuildConfig('foo', fab_workspace=tmp_path)
        svn_export(config, f'file://{workspace.repo_path}/trunk')
        file_tree_compare(workspace.tree_path, source_path)
        assert not (source_path / '.svn').exists()

    def test_extract_from_svn(self, workspace, tmp_path: Path) -> None:
        """
        Checks that a source tree can be extracted from a Subversion
        repository accessed through its own protocol.
        """
        command: List[str] = ['svnserve', '-r', str(workspace.repo_path), '-X']
        process = Popen(command)
        #
        # It seems there can be a delay between the server starting and the
        # listen socket opening. Thus we have a number of retries.
        #
        # TODO: Is there a better solution such that we don't try to connect
        #       until the socket is open?
        #
        source_path = tmp_path / 'bar' / 'source'
        config = BuildConfig('bar', fab_workspace=tmp_path)
        for retry in range(3, 0, -1):
            try:
                svn_export(config, 'svn://localhost/trunk')
            except FabException as ex:
                if range == 0:
                    raise ex
                time.sleep(1.0)
            else:
                break
        file_tree_compare(workspace.tree_path, source_path)
        assert not (source_path / '.svn').exists()

        process.wait(timeout=1)
        assert process.returncode == 0

    @mark.skip(reason="Too hard to test at the moment.")
    def test_extract_from_http(self, repo: Tuple[Path, Path], tmp_path: Path):
        """
        Checks that a source tree can be extracted from a Subversion
        repository accessed through HTTP.

        TODO: This is hard to test without a full Apache installation. For the
              moment we forgo the test on the basis that it's too hard.
        """
        pass
