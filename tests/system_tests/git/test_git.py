# ##############################################################################
#  (c) Crown copyright Met Office. All rights reserved.
#  For further details please refer to the file COPYRIGHT
#  which you should have received as part of this distribution
# ##############################################################################
"""
Test GrabGit.

Most tests are done from a local git repo archived in "tiny_fortran.tar", in this folder.
The repo contains a simple Fortran program which prints an integer variable, foo.

The repo has the following commit structure, each printing a different variable.
 - Head of branch main: foo = 1
 - Head of branch foo2: foo = 22
 - Preceding, tagged commit on foo2: foo = 2

With this we can test grabbing a branch, tag and commit.

"""
import shutil
from pathlib import Path

import pytest

from fab.build_config import BuildConfig
from fab.steps.grab.git import __current_commit, git_checkout, git_merge


@pytest.fixture
def config(tmp_path):
    return BuildConfig('proj', fab_workspace=tmp_path)


class TestGitCheckout(object):
    # Check we can fetch from github.
    @pytest.fixture
    def url(self):
        return 'https://github.com/metomi/fab-test-data.git'

    def test_checkout_url(self, tmp_path, url, config):
        with pytest.warns(UserWarning, match="_metric_send_conn not set, cannot send metrics"):
            git_checkout(config, src=url, dst_label='tiny_fortran')
            # todo: The commit will keep changing. Perhaps make a non-changing branch
            assert current_commit(config.source_root / 'tiny_fortran') == '3cba55e'

    def test_checkout_branch(self, tmp_path, url, config):
        with pytest.warns(UserWarning, match="_metric_send_conn not set, cannot send metrics"):
            git_checkout(config, src=url, dst_label='tiny_fortran', revision='main')
            assert current_commit(config.source_root / 'tiny_fortran') == '3cba55e'

    def test_checkout_tag(self, tmp_path, url, config):
        with pytest.warns(UserWarning, match="_metric_send_conn not set, cannot send metrics"):
            git_checkout(config, src=url, dst_label='tiny_fortran', revision='early')
            assert current_commit(config.source_root / 'tiny_fortran') == 'ee56489'

    def test_checkout_commit(self, tmp_path, url, config):
        with pytest.warns(UserWarning, match="_metric_send_conn not set, cannot send metrics"):
            git_checkout(config, src=url, dst_label='tiny_fortran', revision='ee5648928893701c5dbccdbf0561c0038352a5ff')
            assert current_commit(config.source_root / 'tiny_fortran') == 'ee56489'


# todo: we could do with a test to ensure left-over files from previous fetches are cleaned away


class TestGitMerge(object):

    @pytest.fixture
    def repo_url(self, tmp_path):
        shutil.unpack_archive(Path(__file__).parent / 'repo.tar.gz', tmp_path)
        return f'file://{tmp_path}/repo'

    @pytest.mark.filterwarnings("ignore: Python 3.14 will, "
                                "by default, filter extracted tar archives "
                                "and reject files or modify their metadata. "
                                "Use the filter argument to control this behavior.")
    def test_vanilla(self, repo_url, config):

        # checkout master
        with pytest.warns(UserWarning, match="_metric_send_conn not set, cannot send metrics"):
            git_checkout(config, src=repo_url, dst_label='tiny_fortran', revision='master')
            check_file = config.source_root / 'tiny_fortran/file1.txt'
            assert 'This is sentence one in file one.' in open(check_file).read()

        with pytest.warns(UserWarning, match="_metric_send_conn not set, cannot send metrics"):
            git_merge(config, src=repo_url, dst_label='tiny_fortran', revision='experiment_a')
            assert 'This is sentence one, with Experiment A modification.' in open(check_file).read()

        with pytest.raises(RuntimeError):
            git_merge(config, src=repo_url, dst_label='tiny_fortran', revision='experiment_b')

        # The conflicted merge must have been aborted, check that we can do another checkout of master
        with pytest.warns(UserWarning, match="_metric_send_conn not set, cannot send metrics"):
            git_checkout(config, src=repo_url, dst_label='tiny_fortran', revision='master')
