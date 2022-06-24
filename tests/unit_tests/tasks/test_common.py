"""
Test test_common.py.

"""
from pathlib import Path
from unittest import mock

from fab.constants import COMPILED_FILES

from fab.steps.archive_objects import ArchiveObjects
from fab.steps.link_exe import LinkExe


class TestLinkExe(object):
    def test_run(self):
        # ensure the command is formed correctly, with the flags at the end (why?!)
        linker = LinkExe(linker='foolink', flags=['-fooflag', '-barflag'])

        with mock.patch('os.getenv', return_value='-L/foo1/lib -L/foo2/lib'):
            with mock.patch('fab.steps.link_exe.run_command') as mock_run:
                linker.run(
                    artefact_store={COMPILED_FILES: {'foo': {'foo.o', 'bar.o'}}},
                    config=mock.Mock(project_workspace=Path('workspace')))

        mock_run.assert_called_with([
            'foolink', '-o', 'workspace/foo.exe',
            *sorted(['foo.o', 'bar.o']),
            '-L/foo1/lib', '-L/foo2/lib',
            '-fooflag', '-barflag',
        ])


class TestArchiveObjects(object):
    def test_run(self):
        # ensure the command is formed correctly, with the output filename before the contents
        archiver = ArchiveObjects(archiver='fooarc', output_fpath='$output/foo.a')

        with mock.patch('fab.steps.archive_objects.run_command') as mock_run:
            artefact_store = {COMPILED_FILES: {None: {'foo.o', 'bar.o'}}}
            archiver.run(artefact_store=artefact_store, config=mock.Mock(project_workspace=Path('workspace')))

        mock_run.assert_called_with(['fooarc', 'cr', 'workspace/build_output/foo.a', *sorted(['foo.o', 'bar.o'])])
