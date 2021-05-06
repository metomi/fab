##############################################################################
# (c) Crown copyright Met Office. All rights reserved.
# For further details please refer to the file COPYRIGHT
# which you should have received as part of this distribution
##############################################################################
import logging
from pathlib import Path
from textwrap import dedent

import pytest  # type: ignore

from fab.database import SqliteStateDatabase, WorkingStateException
from fab.tasks.c import \
    CAnalyser, \
    CInfo, \
    CPreProcessor, \
    CPragmaInjector, \
    CCompiler, \
    CSymbolID, \
    CSymbolUnresolvedID, \
    CWorkingState
from fab.artifact import \
    Artifact, \
    CSource, \
    Raw, \
    Analysed, \
    HeadersAnalysed, \
    Seen, \
    Compiled, \
    Modified, \
    BinaryObject


class TestCSymbolUnresolvedID:
    def test_constructor(self):
        test_unit = CSymbolUnresolvedID('thumper')
        assert test_unit.name == 'thumper'

    def test_equality(self):
        test_unit = CSymbolUnresolvedID('dumper')
        with pytest.raises(TypeError):
            _ = test_unit == 'Not a CSymbolUnresolvedID'

        other = CSymbolUnresolvedID('dumper')
        assert test_unit == other
        assert other == test_unit

        other = CSymbolUnresolvedID('trumper')
        assert test_unit != other
        assert other != test_unit


class TestCSymbolID:
    def test_constructor(self):
        test_unit = CSymbolID('beef', Path('cheese'))
        assert test_unit.name == 'beef'
        assert test_unit.found_in == Path('cheese')

    def test_hash(self):
        test_unit = CSymbolID('grumper', Path('bumper'))
        similar = CSymbolID('grumper', Path('bumper'))
        different = CSymbolID('bumper', Path('grumper'))
        assert hash(test_unit) == hash(similar)
        assert hash(test_unit) != hash(different)

    def test_equality(self):
        test_unit = CSymbolID('salt', Path('pepper'))
        with pytest.raises(TypeError):
            _ = test_unit == 'Not a CSymbolID'

        other = CSymbolID('salt', Path('pepper'))
        assert test_unit == other
        assert other == test_unit

        other = CSymbolID('stew', Path('dumplings'))
        assert test_unit != other
        assert other != test_unit


class TestCInfo:
    def test_default_constructor(self):
        test_unit \
            = CInfo(CSymbolID('argle',
                              Path('bargle/wargle.gargle')))
        assert test_unit.symbol.name == 'argle'
        assert test_unit.symbol.found_in == Path('bargle/wargle.gargle')
        assert test_unit.depends_on == []

    def test_prereq_constructor(self):
        test_unit \
            = CInfo(CSymbolID('argle',
                              Path('bargle/wargle.gargle')),
                    ['cheese'])
        assert test_unit.symbol.name == 'argle'
        assert test_unit.symbol.found_in == Path('bargle/wargle.gargle')
        assert test_unit.depends_on == ['cheese']

    def test_equality(self):
        test_unit \
            = CInfo(CSymbolID('argle',
                              Path('bargle/wargle.gargle')),
                    ['beef', 'cheese'])
        with pytest.raises(TypeError):
            _ = test_unit == 'not a CInfo'

        other = CInfo(CSymbolID('argle',
                                Path('bargle/wargle.gargle')),
                      ['beef', 'cheese'])
        assert test_unit == other
        assert other == test_unit

        other = CInfo(CSymbolID('argle',
                                Path('bargle/wargle.gargle')))
        assert test_unit != other
        assert other != test_unit

    def test_add_prerequisite(self):
        test_unit \
            = CInfo(CSymbolID('argle',
                              Path('bargle/wargle.gargle')))
        assert test_unit.depends_on == []

        test_unit.add_prerequisite('cheese')
        assert test_unit.depends_on == ['cheese']


class TestCWorkingSpace:
    def test_add_remove_sequence(self, tmp_path: Path):
        database = SqliteStateDatabase(tmp_path)
        test_unit = CWorkingState(database)
        assert list(iter(test_unit)) == []

        # Add a file containing a program unit and an unsatisfied dependency.
        #
        test_unit.add_c_symbol(CSymbolID('foo', Path('foo.c')))
        test_unit.add_c_dependency(CSymbolID('foo', Path('foo.c')),
                                   'bar')
        assert list(iter(test_unit)) \
            == [CInfo(CSymbolID('foo', Path('foo.c')),
                      ['bar'])]
        assert list(test_unit.depends_on(CSymbolID('foo',
                                                   Path('foo.c')))) \
            == [CSymbolUnresolvedID('bar')]

        # Add a second file containing a second program unit.
        #
        # This satisfies the previously dangling dependency and adds a new
        # one.
        #
        test_unit.add_c_symbol(CSymbolID('bar', Path('bar.c')))
        test_unit.add_c_dependency(CSymbolID('bar', Path('bar.c')),
                                   'baz')
        assert list(iter(test_unit)) \
            == [CInfo(CSymbolID('bar', Path('bar.c')),
                      ['baz']),
                CInfo(CSymbolID('foo', Path('foo.c')),
                      ['bar'])]
        assert list(test_unit.depends_on(CSymbolID('foo',
                                                   Path('foo.c')))) \
            == [CSymbolID('bar', Path('bar.c'))]
        assert list(test_unit.depends_on(CSymbolID('bar',
                                                   Path('bar.c')))) \
            == [CSymbolUnresolvedID('baz')]

        # Add a third file also containing a third program unit and another
        # copy of the first.
        #
        # The new unit depends on two other units.
        #
        test_unit.add_c_symbol(CSymbolID('baz', Path('baz.c')))
        test_unit.add_c_symbol(CSymbolID('foo', Path('baz.c')))
        test_unit.add_c_dependency(CSymbolID('baz', Path('baz.c')),
                                   'qux')
        test_unit.add_c_dependency(CSymbolID('baz', Path('baz.c')),
                                   'cheese')
        assert list(iter(test_unit)) \
            == [CInfo(CSymbolID('bar', Path('bar.c')),
                      ['baz']),
                CInfo(CSymbolID('baz', Path('baz.c')),
                      ['cheese', 'qux']),
                CInfo(CSymbolID('foo', Path('baz.c'))),
                CInfo(CSymbolID('foo', Path('foo.c')),
                      ['bar'])]
        assert list(test_unit.depends_on(CSymbolID('foo',
                                                   Path('foo.c')))) \
            == [CSymbolID('bar', Path('bar.c'))]
        assert list(test_unit.depends_on(CSymbolID('foo',
                                                   Path('baz.c')))) \
            == []
        assert list(test_unit.depends_on(CSymbolID('bar',
                                                   Path('bar.c')))) \
            == [CSymbolID('baz', Path('baz.c'))]
        assert list(test_unit.depends_on(CSymbolID('baz',
                                                   Path('baz.c')))) \
            == [CSymbolUnresolvedID('qux'),
                CSymbolUnresolvedID('cheese')]

        # Remove a previously added file
        #
        test_unit.remove_c_file(Path('baz.c'))
        assert list(iter(test_unit)) \
            == [CInfo(CSymbolID('bar', Path('bar.c')),
                      ['baz']),
                CInfo(CSymbolID('foo', Path('foo.c')),
                      ['bar'])]
        assert list(test_unit.depends_on(CSymbolID('foo',
                                                   Path('foo.c')))) \
            == [CSymbolID('bar', Path('bar.c'))]
        assert list(test_unit.depends_on(CSymbolID('bar',
                                                   Path('bar.c')))) \
            == [CSymbolUnresolvedID('baz')]

    def test_get_symbol(self, tmp_path: Path):
        database = SqliteStateDatabase(tmp_path)
        test_unit = CWorkingState(database)

        # Test on an empty list
        #
        with pytest.raises(WorkingStateException):
            _ = test_unit.get_symbol('tigger')

        # Test we can retrieve an item from a single element list
        test_unit.add_c_symbol(CSymbolID('tigger', Path('tigger.c')))
        assert test_unit.get_symbol('tigger') \
            == [CInfo(CSymbolID('tigger', Path('tigger.c')))]
        with pytest.raises(WorkingStateException):
            _ = test_unit.get_symbol('eeor')

        # Test retrieval from a multi-element list and with prerequisites.
        #
        test_unit.add_c_symbol(CSymbolID('eeor', Path('eeor.c')))
        test_unit.add_c_dependency(CSymbolID('eeor', Path('eeor.c')),
                                   'pooh')
        test_unit.add_c_dependency(CSymbolID('eeor', Path('eeor.c')),
                                   'piglet')
        assert test_unit.get_symbol('tigger') \
            == [CInfo(CSymbolID('tigger', Path('tigger.c')))]
        assert test_unit.get_symbol('eeor') \
            == [CInfo(CSymbolID('eeor', Path('eeor.c')),
                      ['piglet', 'pooh'])]
        with pytest.raises(WorkingStateException):
            _ = test_unit.get_symbol('pooh')

        # Test a multiply defined program unit.
        #
        test_unit.add_c_symbol(CSymbolID('tigger', Path('hundred.c')))
        assert test_unit.get_symbol('tigger') \
            == [CInfo(CSymbolID('tigger', Path('hundred.c'))),
                CInfo(CSymbolID('tigger', Path('tigger.c')))]
        assert test_unit.get_symbol('eeor') \
            == [CInfo(CSymbolID('eeor', Path('eeor.c')),
                      ['piglet', 'pooh'])]
        with pytest.raises(WorkingStateException):
            _ = test_unit.get_symbol('pooh')


class TestCAnalyser(object):
    def test_analyser_symbols(self, caplog, tmp_path):
        """
        Tests that symbols are identified, and calls are
        picked up provided they come from internal headers.
        """
        caplog.set_level(logging.DEBUG)

        test_file: Path = tmp_path / 'test.c'
        test_file.write_text(
            dedent('''
                  #pragma FAB UsrIncludeStart
                  void foo();
                  #pragma FAB UsrIncludeEnd

                  #pragma FAB UsrIncludeStart
                  void bar(int);
                  #pragma FAB UsrIncludeEnd

                  #pragma FAB SysIncludeStart
                  void baz();
                  #pragma FAB SysIncludeEnd

                  #pragma FAB UsrIncludeStart
                  extern int *qux;
                  #pragma FAB UsrIncludeEnd

                  void foo() {
                      bar(qux);
                      baz();
                  }
                   '''))

        database: SqliteStateDatabase = SqliteStateDatabase(tmp_path)
        test_unit = CAnalyser(tmp_path)
        test_artifact = Artifact(test_file,
                                 CSource,
                                 Raw)
        output_artifacts = test_unit.run([test_artifact])

        # Confirm database is updated
        working_state = CWorkingState(database)
        assert list(working_state) \
            == [CInfo(CSymbolID('foo', test_file),
                      ['bar', 'qux'])]

        # Confirm returned Artifact is updated
        assert len(output_artifacts) == 1
        assert output_artifacts[0].defines == ['foo']
        assert output_artifacts[0].depends_on == ['bar', 'qux']
        assert output_artifacts[0].location == test_file
        assert output_artifacts[0].filetype is CSource
        assert output_artifacts[0].state is Analysed


class TestCPragmaInjector:
    def test_run(self, tmp_path):
        workspace = tmp_path / 'working'
        workspace.mkdir()

        test_file: Path = tmp_path / 'test.c'
        test_file.write_text(
            dedent('''
                   #include "user_include.h"
                   Unrelated text
                   #include 'another_user_include.h'
                   #include <system_include.h>
                   More unrelated text
                   #include <another_system_include.h>
                   '''))
        test_artifact = Artifact(test_file,
                                 CSource,
                                 HeadersAnalysed)
        test_artifact.add_dependency('foo')

        # Run the Injector
        injector = CPragmaInjector(workspace)
        artifacts_out = injector.run([test_artifact])

        assert len(artifacts_out) == 1
        assert artifacts_out[0].location == workspace / 'test.c'
        assert artifacts_out[0].filetype is CSource
        assert artifacts_out[0].state is Modified
        assert artifacts_out[0].depends_on == ['foo']
        assert artifacts_out[0].defines == []

        new_file = workspace / 'test.c'
        assert new_file.exists()
        with new_file.open('r') as fh:
            new_text = fh.read()

        expected_text = (
            dedent('''
                   #pragma FAB UsrIncludeStart
                   #include "user_include.h"
                   #pragma FAB UsrIncludeEnd
                   Unrelated text
                   #pragma FAB UsrIncludeStart
                   #include 'another_user_include.h'
                   #pragma FAB UsrIncludeEnd
                   #pragma FAB SysIncludeStart
                   #include <system_include.h>
                   #pragma FAB SysIncludeEnd
                   More unrelated text
                   #pragma FAB SysIncludeStart
                   #include <another_system_include.h>
                   #pragma FAB SysIncludeEnd
                   '''))

        assert new_text == expected_text


class TestCPreProcessor(object):
    def test_run(self, mocker, tmp_path: Path):
        # Instantiate Preprocessor
        workspace = tmp_path / 'working'
        workspace.mkdir()
        preprocessor = CPreProcessor('foo',
                                     ['--bar', '--baz'],
                                     workspace)

        # Create artifact
        artifact = Artifact(Path(tmp_path / 'foo.c'),
                            CSource,
                            Seen)

        # Monkeypatch the subprocess call out and run
        patched_run = mocker.patch('subprocess.run')
        artifacts_out = preprocessor.run([artifact])

        # Check that the subprocess call contained the command
        # that we would expect based on the above
        expected_pp_command = ['foo',
                               '--bar',
                               '--baz',
                               str(tmp_path / 'foo.c'),
                               str(workspace / 'foo.fabcpp')]
        patched_run.assert_any_call(expected_pp_command,
                                    check=True)

        expected_mv_command = ['mv',
                               str(workspace / 'foo.fabcpp'),
                               str(workspace / 'foo.c')]
        patched_run.assert_any_call(expected_mv_command,
                                    check=True)

        assert len(artifacts_out) == 1
        assert artifacts_out[0].location == workspace / 'foo.c'
        assert artifacts_out[0].filetype is CSource
        assert artifacts_out[0].state is Raw
        assert artifacts_out[0].depends_on == []
        assert artifacts_out[0].defines == []


class TestCCompiler(object):
    def test_run(self, mocker, tmp_path: Path):
        # Instantiate Compiler
        workspace = tmp_path / 'working'
        workspace.mkdir()
        compiler = CCompiler('fred',
                             ['--barney', '--wilma'],
                             workspace)

        # Create artifact
        artifact = Artifact(Path(tmp_path / 'flintstone.c'),
                            CSource,
                            Analysed)

        # Monkeypatch the subprocess call out and run
        patched_run = mocker.patch('subprocess.run')
        artifacts_out = compiler.run([artifact])

        # Check that the subprocess call contained the command
        # that we would expect based on the above
        expected_command = ['fred',
                            '--barney',
                            '--wilma',
                            str(tmp_path / 'flintstone.c'),
                            '-o',
                            str(workspace / 'flintstone.o')]
        patched_run.assert_any_call(expected_command,
                                    check=True)

        assert len(artifacts_out) == 1
        assert artifacts_out[0].location == workspace / 'flintstone.o'
        assert artifacts_out[0].filetype is BinaryObject
        assert artifacts_out[0].state is Compiled
        assert artifacts_out[0].depends_on == []
        assert artifacts_out[0].defines == []
