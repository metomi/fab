"""
Test CAnalyser.

"""
from pytest import importorskip
importorskip("clang")

from pathlib import Path
from typing import List, Tuple
from unittest import mock
from unittest.mock import Mock

import clang  # type: ignore

from fab.build_config import BuildConfig
from fab.parse.c import CAnalyser, AnalysedC


def test_simple_result(tmp_path):
    c_analyser = CAnalyser()
    c_analyser._config = BuildConfig('proj', fab_workspace=tmp_path)

    with mock.patch('fab.parse.AnalysedFile.save'):
        fpath = Path(__file__).parent / "test_c_analyser.c"
        analysis, artefact = c_analyser.run(fpath)

    expected = AnalysedC(
        fpath=fpath,
        file_hash=1429445462,
        symbol_deps={'usr_var', 'usr_func'},
        symbol_defs={'func_decl', 'func_def', 'var_def', 'var_extern_def', 'main'},
    )
    assert analysis == expected
    assert artefact == c_analyser._config.prebuild_folder / f'test_c_analyser.{analysis.file_hash}.an'


class Test__locate_include_regions(object):

    def test_vanilla(self):
        lines: List[Tuple[int, str]] = [
            (5, "foo"),
            (10, "# pragma FAB SysIncludeStart"),
            (15, "foo"),
            (20, "# pragma FAB SysIncludeEnd"),
            (25, "foo"),
            (30, "# pragma FAB UsrIncludeStart"),
            (35, "foo"),
            (40, "# pragma FAB UsrIncludeEnd"),
        ]

        self._run(lines=lines, expect=[
            (10, "sys_include_start"),
            (20, "sys_include_end"),
            (30, "usr_include_start"),
            (40, "usr_include_end"),
        ])

    def test_empty_file(self):
        self._run(lines=[], expect=[])

    def _run(self, lines, expect):
        class MockToken(object):
            def __init__(self, spelling, line):
                self.spelling = spelling
                self.location = Mock(line=line)

        tokens = []
        for line in lines:
            tokens.extend(map(lambda token: MockToken(line=line[0], spelling=token), line[1].split()))

        mock_trans_unit = Mock()
        mock_trans_unit.cursor.get_tokens.return_value = tokens

        analyser = CAnalyser()
        analyser._locate_include_regions(mock_trans_unit)

        assert analyser._include_region == expect


class Test__check_for_include(object):

    def test_vanilla(self):
        analyser = CAnalyser()
        analyser._include_region = [
            (10, "sys_include_start"),
            (20, "sys_include_end"),
            (30, "usr_include_start"),
            (40, "usr_include_end"),
        ]

        assert analyser._check_for_include(5) is None
        assert analyser._check_for_include(15) == "sys_include"
        assert analyser._check_for_include(25) is None
        assert analyser._check_for_include(35) == "usr_include"
        assert analyser._check_for_include(45) is None


class Test_process_symbol_declaration(object):

    # definitions
    def test_external_definition(self):
        analysed_file = self._definition(spelling="foo", linkage=clang.cindex.LinkageKind.EXTERNAL)
        analysed_file.add_symbol_def.assert_called_with("foo")

    def test_internal_definition(self):
        analysed_file = self._definition(spelling=None, linkage=clang.cindex.LinkageKind.INTERNAL)
        analysed_file.add_symbol_def.assert_not_called()

    def _definition(self, spelling, linkage):
        node = Mock()
        node.is_definition.return_value = True
        node.linkage = linkage
        node.spelling = spelling

        analyser = CAnalyser()
        analysed_file = Mock()

        analyser._process_symbol_declaration(analysed_file=analysed_file, node=node, usr_symbols=None)

        return analysed_file

    # declarations
    def test_usr_declaration(self):
        usr_symbols = self._declaration(spelling="foo", include_type="usr_include")
        assert usr_symbols == ["foo"]

    def test_not_usr_declaration(self):
        usr_symbols = self._declaration(spelling="foo", include_type="sys_include")
        assert usr_symbols == []

    def _declaration(self, spelling, include_type):
        node = Mock()
        node.is_definition.return_value = False
        node.spelling = spelling

        analyser = CAnalyser()
        analyser._check_for_include = Mock(return_value=include_type)

        usr_symbols = []

        analyser._process_symbol_declaration(analysed_file=None, node=node, usr_symbols=usr_symbols)

        return usr_symbols


class Test_process_symbol_dependency(object):

    def test_usr_symbol(self):
        analysed_file = self._dependency(spelling="foo", usr_symbols=["foo"])
        analysed_file.add_symbol_dep.assert_called_with("foo")

    def test_not_usr_symbol(self):
        analysed_file = self._dependency(spelling="foo", usr_symbols=[])
        analysed_file.add_symbol_dep.assert_not_called()

    def _dependency(self, spelling, usr_symbols):
        analyser = CAnalyser()
        analysed_file = Mock()
        node = Mock(spelling=spelling)

        analyser._process_symbol_dependency(analysed_file, node, usr_symbols)

        return analysed_file


def test_clang_disable():

    with mock.patch('fab.parse.c.clang', None):
        with mock.patch('fab.parse.c.file_checksum') as mock_file_checksum:
            result = CAnalyser().run(Path(__file__).parent / "test_c_analyser.c")

    assert isinstance(result[0], ImportWarning)
    mock_file_checksum.assert_not_called()
