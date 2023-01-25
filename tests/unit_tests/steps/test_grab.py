##############################################################################
# (c) Crown copyright Met Office. All rights reserved.
# For further details please refer to the file COPYRIGHT
# which you should have received as part of this distribution
##############################################################################
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from fab.steps.grab.fcm import GrabFcm
from fab.steps.grab.folder import GrabFolder


class TestGrabFolder(object):

    def test_trailing_slash(self):
        self._common(grab_src='/grab/source/', expect_grab_src='/grab/source/')

    def test_no_trailing_slash(self):
        self._common(grab_src='/grab/source', expect_grab_src='/grab/source/')

    def _common(self, grab_src, expect_grab_src):
        source_root = Path('/workspace/source')
        dst = 'bar'
        grabber = GrabFolder(src=grab_src, dst=dst)

        mock_config = SimpleNamespace(source_root=source_root)
        with mock.patch('pathlib.Path.mkdir'):
            with mock.patch('fab.steps.grab.run_command') as mock_run:
                grabber.run(artefact_store={}, config=mock_config)

        expect_dst = mock_config.source_root / dst
        mock_run.assert_called_once_with(['rsync', '--times', '--stats', '-ru', expect_grab_src, str(expect_dst)])


class TestGrabFcm(object):

    def test_no_revision(self):
        source_root = Path('/workspace/source')
        source_url = '/www.example.com/bar'
        dst_label = 'bar'
        grabber = GrabFcm(src=source_url, dst=dst_label)

        mock_config = SimpleNamespace(source_root=source_root)
        with mock.patch('pathlib.Path.mkdir'):
            with mock.patch('fab.steps.grab.fcm.run_command') as mock_run:
                grabber.run(artefact_store={}, config=mock_config)

        mock_run.assert_called_once_with(['fcm', 'export', '--force', source_url, str(source_root / dst_label)])

    def test_revision(self):
        source_root = Path('/workspace/source')
        source_url = '/www.example.com/bar'
        dst_label = 'bar'
        revision = '42'
        grabber = GrabFcm(src=source_url, dst=dst_label, revision=revision)

        mock_config = SimpleNamespace(source_root=source_root)
        with mock.patch('pathlib.Path.mkdir'):
            with mock.patch('fab.steps.grab.fcm.run_command') as mock_run:
                grabber.run(artefact_store={}, config=mock_config)

        mock_run.assert_called_once_with(
            ['fcm', 'export', '--force', f'{source_url}@{revision}', str(source_root / dst_label)])

    # todo: test missing repo
    # def test_missing(self):
    #     assert False


# todo: test GrabSvn
# class TestGrabSvn(object):
#     def test(self):
#         assert False
