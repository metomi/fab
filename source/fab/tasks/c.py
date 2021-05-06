# (c) Crown copyright Met Office. All rights reserved.
# For further details please refer to the file COPYRIGHT
# which you should have received as part of this distribution
"""
C language handling classes.
"""
import logging
import subprocess
import re
import clang.cindex  # type: ignore
from collections import deque
from typing import \
    List, \
    Iterator, \
    Pattern, \
    Optional, \
    Match, \
    Sequence, \
    Generator, \
    Union
from pathlib import Path

from fab.database import \
    StateDatabase, \
    DatabaseDecorator, \
    FileInfoDatabase, \
    SqliteStateDatabase, \
    WorkingStateException
from fab.tasks import Task, TaskException
from fab.artifact import \
    Artifact, \
    Raw, \
    Modified, \
    Analysed, \
    Compiled, \
    BinaryObject
from fab.reader import \
    TextReader, \
    FileTextReader, \
    TextReaderDecorator


class CSymbolUnresolvedID(object):
    def __init__(self, name: str):
        self.name = name

    def __eq__(self, other):
        if not isinstance(other, CSymbolUnresolvedID):
            message = "Cannot compare CSymbolUnresolvedID with " \
                + other.__class__.__name__
            raise TypeError(message)
        return other.name == self.name


class CSymbolID(CSymbolUnresolvedID):
    def __init__(self, name: str, found_in: Path):
        super().__init__(name)
        self.found_in = found_in

    def __hash__(self):
        return hash(self.name) + hash(self.found_in)

    def __eq__(self, other):
        if not isinstance(other, CSymbolID):
            message = "Cannot compare CSymbolID with " \
                + other.__class__.__name__
            raise TypeError(message)
        return super().__eq__(other) and other.found_in == self.found_in


class CInfo(object):
    def __init__(self,
                 symbol: CSymbolID,
                 depends_on: Sequence[str] = ()):
        self.symbol = symbol
        self.depends_on = list(depends_on)

    def __str__(self):
        return f"C symbol '{self.symbol.name}' " \
            f"from '{self.symbol.found_in}' depending on: " \
            f"{', '.join(self.depends_on)}"

    def __eq__(self, other):
        if not isinstance(other, CInfo):
            message = "Cannot compare C Info with " \
                + other.__class__.__name__
            raise TypeError(message)
        return other.symbol == self.symbol \
            and other.depends_on == self.depends_on

    def add_prerequisite(self, prereq: str):
        self.depends_on.append(prereq)


class CWorkingState(DatabaseDecorator):
    """
    Maintains a database of information relating to C symbols.
    """
    # According to the C standard, section 5.2.4.1,
    # (C11) ISO/IEC 9899, the maximum length of an
    # external identifier is 31 characters.
    #
    _C_LABEL_LENGTH: int = 31

    def __init__(self, database: StateDatabase):
        super().__init__(database)
        create_symbol_table = [
            f'''create table if not exists c_symbol (
                   id integer primary key,
                   symbol character({self._C_LABEL_LENGTH}) not null,
                   found_in character({FileInfoDatabase.PATH_LENGTH})
                       references file_info (filename)
                   )''',
            '''create index if not exists idx_c_symbol
                   on c_symbol (symbol, found_in)'''
        ]
        self.execute(create_symbol_table, {})

        # Although the current symbol will already have been entered into the
        # database it is not necessarily unique. We may have multiple source
        # files which define identically named symbols. Thus it can not be used
        # as a foreign key alone.
        #
        # Meanwhile the dependency symbol may not have been encountered yet so
        # we can't expect it to be in the database. Thus it too may not be
        # used as a foreign key.
        #
        create_prerequisite_table = [
            f'''create table if not exists c_prerequisite (
                id integer primary key,
                symbol character({self._C_LABEL_LENGTH}) not null,
                found_in character({FileInfoDatabase.PATH_LENGTH}) not null,
                prerequisite character({self._C_LABEL_LENGTH}) not null,
                foreign key (symbol, found_in)
                references c_symbol (symbol, found_in)
                )'''
        ]
        self.execute(create_prerequisite_table, {})

    def __iter__(self) -> Generator[CInfo, None, None]:
        """
        Yields all symbols and their containing file names.
        :return: Object per symbol.
        """
        query = '''select s.symbol as name, s.found_in, p.prerequisite as prereq
                   from c_symbol as s
                   left join c_prerequisite as p
                   on p.symbol = s.symbol and p.found_in = s.found_in
                   order by s.symbol, s.found_in, p.prerequisite'''
        rows = self.execute([query], {})
        info: Optional[CInfo] = None
        key: CSymbolID = CSymbolID('', Path())
        for row in rows:
            if CSymbolID(row['name'], Path(row['found_in'])) == key:
                if info is not None:
                    info.add_prerequisite(row['prereq'])
            else:  # (row['name'], row['found_in']) != key
                if info is not None:
                    yield info
                key = CSymbolID(row['name'], Path(row['found_in']))
                info = CInfo(key)
                if row['prereq']:
                    info.add_prerequisite(row['prereq'])
        if info is not None:  # We have left-overs
            yield info

    def add_c_symbol(self, symbol: CSymbolID) -> None:
        """
        Creates a record of a new symbol and the file it is found in.
        Note that the filename is absolute meaning that if you rename or move
        the source directory nothing will match up.
        :param symbol: symbol identifier.
        """
        add_symbol = [
            '''insert into c_symbol (symbol, found_in)
                   values (:symbol, :filename)'''
        ]
        self.execute(add_symbol,
                     {'symbol': symbol.name,
                      'filename': str(symbol.found_in)})

    def add_c_dependency(self,
                         symbol: CSymbolID,
                         depends_on: str) -> None:
        """
        Records the dependency of one symbol on another.
        :param symbol: symbol identifier.
        :param depends_on: Name of the prerequisite symbol.
        """
        add_dependency = [
            '''insert into c_prerequisite(symbol, found_in, prerequisite)
                   values (:symbol, :found_in, :depends_on)'''
        ]
        self.execute(add_dependency, {'symbol': symbol.name,
                                      'found_in': str(symbol.found_in),
                                      'depends_on': depends_on})

    def remove_c_file(self, filename: Union[Path, str]) -> None:
        """
        Removes all records relating of a particular source file.
        :param filename: File to be removed.
        """
        remove_file = [
            '''delete from c_prerequisite
               where found_in = :filename''',
            '''delete from c_symbol where found_in=:filename'''
            ]
        self.execute(remove_file, {'filename': str(filename)})

    def get_symbol(self, name: str) -> List[CInfo]:
        """
        Gets the details of symbols given their name.
        It is possible that identically named symbols appear in multiple
        files, hence why a list is returned. It would be an error to try
        linking these into a single executable but that is not a concern for
        the model of the source tree.
        :param name: symbol name.
        :return: List of symbol information objects.
        """
        query = '''select s.symbol, s.found_in, p.prerequisite
                   from c_symbol as s
                   left join c_prerequisite as p
                   on p.symbol = s.symbol and p.found_in = s.found_in
                   where s.symbol=:symbol
                   order by s.symbol, s.found_in, p.prerequisite'''
        rows = self.execute(query, {'symbol': name})
        info_list: List[CInfo] = []
        previous_id = None
        info: Optional[CInfo] = None
        for row in rows:
            symbol_id = CSymbolID(row['symbol'], Path(row['found_in']))
            if previous_id is not None and symbol_id == previous_id:
                if info is not None:
                    info.add_prerequisite(row['prerequisite'])
            else:  # symbol_id != previous_id
                if info is not None:
                    info_list.append(info)
                info = CInfo(symbol_id)
                if row['prerequisite'] is not None:
                    info.add_prerequisite((row['prerequisite']))
                previous_id = symbol_id
        if info is not None:  # We have left overs
            info_list.append(info)
        if len(info_list) == 0:
            message = 'symbol "{symbol}" not found in database.'
            raise WorkingStateException(message.format(symbol=name))
        return info_list

    def depends_on(self, symbol: CSymbolID)\
            -> Generator[CSymbolID, None, None]:
        """
        Gets the prerequisite symbols of a symbol.
        :param symbol: symbol identifier.
        :return: Prerequisite symbol names. May be an empty list.
        """
        query = '''select p.prerequisite, f.found_in
                   from c_prerequisite as p
                   left join c_symbol as f on f.symbol = p.prerequisite
                   where p.symbol=:symbol and p.found_in=:filename
                   order by p.symbol, f.found_in'''
        rows = self.execute(query, {'symbol': symbol.name,
                                    'filename': str(symbol.found_in)})
        for row in rows:
            if row['found_in'] is None:
                yield CSymbolUnresolvedID(row['prerequisite'])
            else:  # row['found_in'] is not None
                yield CSymbolID(row['prerequisite'], Path(row['found_in']))


class CAnalyser(Task):
    def __init__(self, workspace: Path):
        self.database = SqliteStateDatabase(workspace)

    def _locate_include_regions(self, trans_unit) -> None:
        # Aim is to identify where included (top level) regions
        # start and end in the file
        self._include_region = []

        # Use a deque to implement a rolling window of 4 identifiers
        # (enough to be sure we can spot an entire pragma)
        identifiers: deque = deque([])
        for token in trans_unit.cursor.get_tokens():
            identifiers.append(token)
            if len(identifiers) < 4:
                continue
            if len(identifiers) > 4:
                identifiers.popleft()

            # Trigger off of the FAB identifier only to save
            # on joining the group too frequently
            if identifiers[2].spelling == "FAB":
                lineno = identifiers[2].location.line
                full = " ".join(id.spelling for id in identifiers)
                if full == "# pragma FAB SysIncludeStart":
                    self._include_region.append(
                        (lineno, "sys_include_start"))
                elif full == "# pragma FAB SysIncludeEnd":
                    self._include_region.append(
                        (lineno, "sys_include_end"))
                elif full == "# pragma FAB UsrIncludeStart":
                    self._include_region.append(
                        (lineno, "usr_include_start"))
                elif full == "# pragma FAB UsrIncludeEnd":
                    self._include_region.append(
                        (lineno, "usr_include_end"))

    def _check_for_include(self, lineno) -> Optional[str]:
        # Check whether a given line number is in a region that
        # has come from an include (and return what kind of include)
        include_stack = []
        for region_line, region_type in self._include_region:
            if region_line > lineno:
                break
            if region_type.endswith("start"):
                include_stack.append(region_type.replace("_start", ""))
            elif region_type.endswith("end"):
                include_stack.pop()
        if include_stack:
            return include_stack[-1]
        else:
            return None

    def run(self, artifacts: List[Artifact]) -> List[Artifact]:
        logger = logging.getLogger(__name__)

        if len(artifacts) == 1:
            artifact = artifacts[0]
        else:
            msg = ('C Analyser expects only one Artifact, '
                   f'but was given {len(artifacts)}')
            raise TaskException(msg)

        reader = FileTextReader(artifact.location)

        state = CWorkingState(self.database)
        state.remove_c_file(reader.filename)

        new_artifact = Artifact(artifact.location,
                                artifact.filetype,
                                Analysed)

        state = CWorkingState(self.database)
        state.remove_c_file(reader.filename)

        index = clang.cindex.Index.create()
        translation_unit = index.parse(reader.filename,
                                       args=["-xc"])

        # Create include region line mappings
        self._locate_include_regions(translation_unit)

        # Now walk the actual nodes and find all relevant external symbols
        usr_includes = []
        external_vars = []
        current_def = None
        for node in translation_unit.cursor.walk_preorder():
            logger.debug('Considering node: %s', node.spelling)
            if node.kind == clang.cindex.CursorKind.FUNCTION_DECL:
                logger.debug('  * Is a function declaration')
                if (node.is_definition()
                        and node.linkage == clang.cindex.LinkageKind.EXTERNAL):
                    # This should catch function definitions which are exposed
                    # to the rest of the application
                    logger.debug('  * Is defined in this file')
                    current_def = CSymbolID(node.spelling, artifact.location)
                    state.add_c_symbol(current_def)
                    new_artifact.add_definition(node.spelling)
                else:
                    # Any other declarations should be coming in via headers,
                    # we can use the injected pragmas to work out whether these
                    # are coming from system headers or user headers
                    if (self._check_for_include(node.location.line)
                            == "usr_include"):
                        logger.debug('  * Is not defined in this file')
                        usr_includes.append(node.spelling)

            elif node.kind == clang.cindex.CursorKind.CALL_EXPR:
                # When encountering a function call we should be able to
                # cross-reference it with a definition seen earlier; and
                # if it came from a user supplied header then we will
                # consider it a dependency within the project
                logger.debug('  * Is a function call')
                if node.spelling in usr_includes and current_def is not None:
                    # TODO: Assumption that the most recent exposed
                    # definition encountered above is the one which
                    # should lodge this dependency - is that true?
                    logger.debug('  * Not a std function (so a dependency)')
                    state.add_c_dependency(current_def, node.spelling)
                    new_artifact.add_dependency(node.spelling)

            elif node.kind == clang.cindex.CursorKind.VAR_DECL:
                # Variable definitions can be external too, lodge any
                # encountered in user headers here
                if ((not node.is_definition())
                        and node.linkage == clang.cindex.LinkageKind.EXTERNAL):
                    if (self._check_for_include(node.location.line)
                            == "usr_include"):
                        external_vars.append(node.spelling)

            elif node.kind == clang.cindex.CursorKind.DECL_REF_EXPR:
                # Find references to variables which came in externally (as
                # captured by the list above)
                if node.spelling in external_vars and current_def is not None:
                    # TODO: Assumption that the most recent exposed
                    # definition encountered above is the one which
                    # should lodge this dependency - is that true?
                    state.add_c_dependency(current_def, node.spelling)
                    new_artifact.add_dependency(node.spelling)

        return [new_artifact]


class _CTextReaderPragmas(TextReaderDecorator):
    """
    Reads a C source file but when encountering an #include
    preprocessor directive injects a special Fab-specific
    #pragma which can be picked up later by the Analyser
    after the preprocessing
    """
    def __init__(self, source: TextReader):
        super().__init__(source)
        self._line_buffer = ''

    _include_re: str = r'^\s*#include\s+(\S+)'
    _include_pattern: Pattern = re.compile(_include_re)

    def line_by_line(self) -> Iterator[str]:
        for line in self._source.line_by_line():
            include_match: Optional[Match] \
                = self._include_pattern.match(line)
            if include_match:
                # For valid C the first character of the matched
                # part of the group will indicate whether this is
                # a system library include or a user include
                include: str = include_match.group(1)
                # TODO: Is this sufficient?  Or do the pragmas
                #       need to include identifying info
                #       e.g. the name of the original include?
                if include.startswith('<'):
                    yield '#pragma FAB SysIncludeStart\n'
                    yield line
                    yield '#pragma FAB SysIncludeEnd\n'
                elif include.startswith(('"', "'")):
                    yield '#pragma FAB UsrIncludeStart\n'
                    yield line
                    yield '#pragma FAB UsrIncludeEnd\n'
                else:
                    msg = 'Found badly formatted #include'
                    raise TaskException(msg)
            else:
                yield line


class CPragmaInjector(Task):
    def __init__(self, workspace: Path):
        self._workspace = workspace

    def run(self, artifacts: List[Artifact]) -> List[Artifact]:
        logger = logging.getLogger(__name__)

        if len(artifacts) == 1:
            artifact = artifacts[0]
        else:
            msg = ('C Pragma Injector expects only one Artifact, '
                   f'but was given {len(artifacts)}')
            raise TaskException(msg)

        logger.debug('Injecting pragmas into: %s', artifact.location)
        injector = _CTextReaderPragmas(
            FileTextReader(artifact.location))

        output_file = self._workspace / artifact.location.name

        out_lines = [line for line in injector.line_by_line()]

        with output_file.open('w') as out_file:
            for line in out_lines:
                out_file.write(line)

        new_artifact = Artifact(output_file,
                                artifact.filetype,
                                Modified)
        for dependency in artifact.depends_on:
            new_artifact.add_dependency(dependency)

        return [new_artifact]


class CPreProcessor(Task):
    def __init__(self,
                 preprocessor: str,
                 flags: List[str],
                 workspace: Path):
        self._preprocessor = preprocessor
        self._flags = flags
        self._workspace = workspace

    def run(self, artifacts: List[Artifact]) -> List[Artifact]:
        logger = logging.getLogger(__name__)

        if len(artifacts) == 1:
            artifact = artifacts[0]
        else:
            msg = ('C Preprocessor expects only one Artifact, '
                   f'but was given {len(artifacts)}')
            raise TaskException(msg)

        command = [self._preprocessor]
        command.extend(self._flags)
        command.append(str(artifact.location))

        # Use temporary output name (in case the given tool
        # can't operate in-place)
        output_file = (self._workspace /
                       artifact.location.with_suffix('.fabcpp').name)

        command.append(str(output_file))
        logger.debug('Running command: ' + ' '.join(command))
        subprocess.run(command, check=True)

        # Overwrite actual output file
        final_output = (self._workspace /
                        artifact.location.name)
        command = ["mv", str(output_file), str(final_output)]
        logger.debug('Running command: ' + ' '.join(command))
        subprocess.run(command, check=True)

        return [Artifact(final_output,
                         artifact.filetype,
                         Raw)]


class CCompiler(Task):

    def __init__(self,
                 compiler: str,
                 flags: List[str],
                 workspace: Path):
        self._compiler = compiler
        self._flags = flags
        self._workspace = workspace

    def run(self, artifacts: List[Artifact]) -> List[Artifact]:
        logger = logging.getLogger(__name__)

        if len(artifacts) == 1:
            artifact = artifacts[0]
        else:
            msg = ('C Compiler expects only one Artifact, '
                   f'but was given {len(artifacts)}')
            raise TaskException(msg)

        command = [self._compiler]
        command.extend(self._flags)
        command.append(str(artifact.location))

        output_file = (self._workspace /
                       artifact.location.with_suffix('.o').name)
        command.extend(['-o', str(output_file)])

        logger.debug('Running command: ' + ' '.join(command))
        subprocess.run(command, check=True)

        object_artifact = Artifact(output_file,
                                   BinaryObject,
                                   Compiled)
        for definition in artifact.defines:
            object_artifact.add_definition(definition)

        return [object_artifact]
