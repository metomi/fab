# (c) Crown copyright Met Office. All rights reserved.
# For further details please refer to the file COPYRIGHT
# which you should have received as part of this distribution
"""
Fortran language handling classes.
"""
import logging
from pathlib import Path
import re
import subprocess
from typing import (Generator,
                    Iterator,
                    List,
                    Match,
                    Optional,
                    Pattern,
                    Sequence,
                    Tuple,
                    Union)

from fab.database import (DatabaseDecorator,
                          FileInfoDatabase,
                          StateDatabase,
                          SqliteStateDatabase,
                          WorkingStateException)
from fab.tasks import \
    Task, \
    TaskException
from fab.tasks.c import CWorkingState, CSymbolID
from fab.reader import TextReader, TextReaderDecorator, FileTextReader
from fab.artifact import \
    Artifact, \
    Analysed, \
    Raw, \
    Compiled, \
    BinaryObject


class FortranUnitUnresolvedID(object):
    def __init__(self, name: str):
        self.name = name

    def __eq__(self, other):
        if not isinstance(other, FortranUnitUnresolvedID):
            message = "Cannot compare FortranUnitUnresolvedID with " \
                + other.__class__.__name__
            raise TypeError(message)
        return other.name == self.name


class FortranUnitID(FortranUnitUnresolvedID):
    def __init__(self, name: str, found_in: Path):
        super().__init__(name)
        self.found_in = found_in

    def __hash__(self):
        return hash(self.name) + hash(self.found_in)

    def __eq__(self, other):
        if not isinstance(other, FortranUnitID):
            message = "Cannot compare FortranUnitID with " \
                + other.__class__.__name__
            raise TypeError(message)
        return super().__eq__(other) and other.found_in == self.found_in


class FortranInfo(object):
    def __init__(self,
                 unit: FortranUnitID,
                 depends_on: Sequence[str] = ()):
        self.unit = unit
        self.depends_on = list(depends_on)

    def __str__(self):
        return f"Fortran program unit '{self.unit.name}' " \
            f"from '{self.unit.found_in}' depending on: " \
            f"{', '.join(self.depends_on)}"

    def __eq__(self, other):
        if not isinstance(other, FortranInfo):
            message = "Cannot compare Fortran Info with " \
                + other.__class__.__name__
            raise TypeError(message)
        return other.unit == self.unit and other.depends_on == self.depends_on

    def add_prerequisite(self, prereq: str):
        self.depends_on.append(prereq)


class FortranWorkingState(DatabaseDecorator):
    """
    Maintains a database of information relating to Fortran program units.
    """
    # According to the Fortran spec, section 3.2.2 in
    # BS ISO/IEC 1539-1:2010, the maximum size of a name is 63 characters.
    #
    # If you find source containing labels longer than this then that source
    # is non-conformant.
    #
    _FORTRAN_LABEL_LENGTH: int = 63

    def __init__(self, database: StateDatabase):
        super().__init__(database)
        create_unit_table = [
            f'''create table if not exists fortran_unit (
                   id integer primary key,
                   unit character({self._FORTRAN_LABEL_LENGTH}) not null,
                   found_in character({FileInfoDatabase.PATH_LENGTH})
                       references file_info (filename)
                   )''',
            '''create index if not exists idx_fortran_program_unit
                   on fortran_unit (unit, found_in)'''
        ]
        self.execute(create_unit_table, {})

        # Although the current unit will already have been entered into the
        # database it is not necessarily unique. We may have multiple source
        # files which define identically named units. Thus it can not be used
        # as a foreign key alone.
        #
        # Meanwhile the dependency unit may not have been encountered yet so
        # we can't expect it to be in the database. Thus it too may not be
        # used as a foreign key.
        #
        create_prerequisite_table = [
            f'''create table if not exists fortran_prerequisite (
                id integer primary key,
                unit character({self._FORTRAN_LABEL_LENGTH}) not null,
                found_in character({FileInfoDatabase.PATH_LENGTH}) not null,
                prerequisite character({self._FORTRAN_LABEL_LENGTH}) not null,
                foreign key (unit, found_in)
                references fortran_unit (unit, found_in)
                )'''
        ]
        self.execute(create_prerequisite_table, {})

    def __iter__(self) -> Generator[FortranInfo, None, None]:
        """
        Yields all units and their containing file names.

        :return: Object per unit.
        """
        query = '''select u.unit as name, u.found_in, p.prerequisite as prereq
                   from fortran_unit as u
                   left join fortran_prerequisite as p
                   on p.unit = u.unit and p.found_in = u.found_in
                   order by u.unit, u.found_in, p.prerequisite'''
        rows = self.execute([query], {})
        info: Optional[FortranInfo] = None
        key: FortranUnitID = FortranUnitID('', Path())
        for row in rows:
            if FortranUnitID(row['name'], Path(row['found_in'])) == key:
                if info is not None:
                    info.add_prerequisite(row['prereq'])
            else:  # (row['name'], row['found_in']) != key
                if info is not None:
                    yield info
                key = FortranUnitID(row['name'], Path(row['found_in']))
                info = FortranInfo(key)
                if row['prereq']:
                    info.add_prerequisite(row['prereq'])
        if info is not None:  # We have left-overs
            yield info

    def add_fortran_program_unit(self, unit: FortranUnitID) -> None:
        """
        Creates a record of a new program unit and the file it is found in.

        Note that the filename is absolute meaning that if you rename or move
        the source directory nothing will match up.

        :param unit: Program unit identifier.
        """
        add_unit = [
            '''insert into fortran_unit (unit, found_in)
                   values (:unit, :filename)'''
        ]
        self.execute(add_unit,
                     {'unit': unit.name, 'filename': str(unit.found_in)})

    def add_fortran_dependency(self,
                               unit: FortranUnitID,
                               depends_on: str) -> None:
        """
        Records the dependency of one unit on another.

        :param unit: Program unit identifier.
        :param depends_on: Name of the prerequisite unit.
        """
        add_dependency = [
            '''insert into fortran_prerequisite(unit, found_in, prerequisite)
                   values (:unit, :found_in, :depends_on)'''
        ]
        self.execute(add_dependency, {'unit': unit.name,
                                      'found_in': str(unit.found_in),
                                      'depends_on': depends_on})

    def remove_fortran_file(self, filename: Union[Path, str]) -> None:
        """
        Removes all records relating of a particular source file.

        :param filename: File to be removed.
        """
        remove_file = [
            '''delete from fortran_prerequisite
               where found_in = :filename''',
            '''delete from fortran_unit where found_in=:filename'''
            ]
        self.execute(remove_file, {'filename': str(filename)})

    def get_program_unit(self, name: str) -> List[FortranInfo]:
        """
        Gets the details of program units given their name.

        It is possible that identically named program units appear in multiple
        files, hence why a list is returned. It would be an error to try
        linking these into a single executable but that is not a concern for
        the model of the source tree.

        :param name: Program unit name.
        :return: List of unit information objects.
        """
        query = '''select u.unit, u.found_in, p.prerequisite
                   from fortran_unit as u
                   left join fortran_prerequisite as p
                   on p.unit = u.unit and p.found_in = u.found_in
                   where u.unit=:unit
                   order by u.unit, u.found_in, p.prerequisite'''
        rows = self.execute(query, {'unit': name})
        info_list: List[FortranInfo] = []
        previous_id = None
        info: Optional[FortranInfo] = None
        for row in rows:
            unit_id = FortranUnitID(row['unit'], Path(row['found_in']))
            if previous_id is not None and unit_id == previous_id:
                if info is not None:
                    info.add_prerequisite(row['prerequisite'])
            else:  # unit_id != previous_id
                if info is not None:
                    info_list.append(info)
                info = FortranInfo(unit_id)
                if row['prerequisite'] is not None:
                    info.add_prerequisite((row['prerequisite']))
                previous_id = unit_id
        if info is not None:  # We have left overs
            info_list.append(info)
        if len(info_list) == 0:
            message = 'Program unit "{unit}" not found in database.'
            raise WorkingStateException(message.format(unit=name))
        return info_list

    def depends_on(self, unit: FortranUnitID)\
            -> Generator[FortranUnitID, None, None]:
        """
        Gets the prerequisite program units of a program unit.

        :param unit: Program unit identifier.
        :return: Prerequisite unit names. May be an empty list.
        """
        query = '''select p.prerequisite, u.found_in
                   from fortran_prerequisite as p
                   left join fortran_unit as u on u.unit = p.prerequisite
                   where p.unit=:unit and p.found_in=:filename
                   order by p.unit, u.found_in'''
        rows = self.execute(query, {'unit': unit.name,
                                    'filename': str(unit.found_in)})
        for row in rows:
            if row['found_in'] is None:
                yield FortranUnitUnresolvedID(row['prerequisite'])
            else:  # row['found_in'] is not None
                yield FortranUnitID(row['prerequisite'], Path(row['found_in']))


class FortranNormaliser(TextReaderDecorator):
    def __init__(self, source: TextReader):
        super().__init__(source)
        self._line_buffer = ''

    def line_by_line(self) -> Iterator[str]:
        """
        Each line of the source file is modified to ease the work of analysis.

        The lines are sanitised to remove comments and collapse the result
        of continuation lines whilst also trimming away as much whitespace as
        possible
        """
        for line in self._source.line_by_line():
            # Remove comments - we accept that an exclamation mark
            # appearing in a string will cause the rest of that line
            # to be blanked out, but the things we wish to parse
            # later shouldn't appear after a string on a line anyway
            line = re.sub(r'!.*', '', line)

            # If the line is empty, go onto the next
            if line.strip() == '':
                continue

            # Deal with continuations by removing them to collapse
            # the lines together
            self._line_buffer += line
            if '&' in self._line_buffer:
                self._line_buffer = re.sub(r'&\s*$', '', self._line_buffer)
                continue

            # Before output, minimise whitespace but add a space on the end
            # of the line.
            line_buffer = re.sub(r'\s+', r' ', self._line_buffer)
            yield line_buffer.rstrip()
            self._line_buffer = ''


class FortranAnalyser(Task):
    def __init__(self, workspace: Path):
        self.database = SqliteStateDatabase(workspace)

    _intrinsic_modules = ['iso_fortran_env']

    _letters: str = r'abcdefghijklmnopqrstuvwxyz'
    _digits: str = r'1234567890'
    _underscore: str = r'_'
    _alphanumeric_re: str = '[' + _letters + _digits + _underscore + ']'
    _name_re: str = '[' + _letters + ']' + _alphanumeric_re + '*'
    _procedure_block_re: str = r'function|subroutine'
    _unit_block_re: str = r'program|module|' + _procedure_block_re
    _scope_block_re: str = r'associate|block|critical|do|if|select'
    _iface_block_re: str = r'interface'
    _type_block_re: str = r'type'
    _bind_stmt_re: str = r'bind'

    _program_unit_re: str = r'^\s*({unit_type_re})\s*({name_re})' \
                            .format(unit_type_re=_unit_block_re,
                                    name_re=_name_re)
    _scoping_re: str = r'^\s*(({name_re})\s*:)?\s*({scope_type_re})' \
                       .format(scope_type_re=_scope_block_re,
                               name_re=_name_re)
    _procedure_re: str = r'^\s*({procedure_block_re})\s*({name_re})' \
                         .format(procedure_block_re=_procedure_block_re,
                                 name_re=_name_re)
    _interface_re: str = r'^\s*{iface_block_re}\s*({name_re})?' \
                         .format(iface_block_re=_iface_block_re,
                                 name_re=_name_re)
    _type_re: str = r'^\s*{type_block_re}' \
                    r'((\s*,\s*[^,]+)*\s*::)?' \
                    r'\s*({name_re})'.format(type_block_re=_type_block_re,
                                             name_re=_name_re)
    _end_block_re: str \
        = r'^\s*end' \
          r'\s*({scope_block_re}|{iface_block_re}' \
          r'|{type_block_re}|{unit_type_re})?' \
          r'\s*({name_re})?'.format(scope_block_re=_scope_block_re,
                                    iface_block_re=_iface_block_re,
                                    type_block_re=_type_block_re,
                                    unit_type_re=_unit_block_re,
                                    name_re=_name_re)

    _use_statement_re: str \
        = r'^\s*use((\s*,\s*non_intrinsic)?\s*::)?\s*({name_re})' \
          .format(name_re=_name_re)

    _cbind_statement_re: str \
        = r'.*\W+{bind_re}\s*\(\s*c\s*(\)|,\s*name\s*=(\S+)\s*\)).*' \
          .format(bind_re=_bind_stmt_re)

    _program_unit_pattern: Pattern = re.compile(_program_unit_re,
                                                re.IGNORECASE)
    _scoping_pattern: Pattern = re.compile(_scoping_re, re.IGNORECASE)
    _procedure_pattern: Pattern = re.compile(_procedure_re, re.IGNORECASE)
    _interface_pattern: Pattern = re.compile(_interface_re, re.IGNORECASE)
    _type_pattern: Pattern = re.compile(_type_re, re.IGNORECASE)
    _end_block_pattern: Pattern = re.compile(_end_block_re, re.IGNORECASE)
    _use_pattern: Pattern = re.compile(_use_statement_re, re.IGNORECASE)
    _cbind_pattern: Pattern = re.compile(_cbind_statement_re, re.IGNORECASE)

    def run(self, artifacts: List[Artifact]) -> List[Artifact]:
        logger = logging.getLogger(__name__)

        if len(artifacts) == 1:
            artifact = artifacts[0]
        else:
            msg = ('Fortran Analyser expects only one Artifact, '
                   f'but was given {len(artifacts)}')
            raise TaskException(msg)

        reader = FileTextReader(artifact.location)

        new_artifact = Artifact(artifact.location,
                                artifact.filetype,
                                Analysed)

        state = FortranWorkingState(self.database)
        state.remove_fortran_file(reader.filename)
        logger.debug('Analysing: %s', reader.filename)

        # If this file defines any C symbol bindings it may also
        # end up with an entry in the C part of the database
        cstate = CWorkingState(self.database)
        cstate.remove_c_file(reader.filename)

        normalised_source = FortranNormaliser(reader)
        scope: List[Tuple[str, str]] = []
        for line in normalised_source.line_by_line():
            logger.debug(scope)
            logger.debug('Considering: %s', line)

            if len(scope) == 0:
                unit_match: Optional[Match] \
                    = self._program_unit_pattern.match(line)
                if unit_match:
                    unit_type: str = unit_match.group(1).lower()
                    unit_name: str = unit_match.group(2).lower()
                    logger.debug('Found %s called "%s"', unit_type, unit_name)
                    unit_id = FortranUnitID(unit_name, reader.filename)
                    state.add_fortran_program_unit(unit_id)
                    new_artifact.add_definition(unit_name)
                    scope.append((unit_type, unit_name))
                    continue
            use_match: Optional[Match] \
                = self._use_pattern.match(line)
            if use_match:
                use_name: str = use_match.group(3).lower()
                if use_name in self._intrinsic_modules:
                    logger.debug('Ignoring intrinsic module "%s"', use_name)
                else:
                    if len(scope) == 0:
                        use_message \
                            = '"use" statement found outside program unit'
                        raise TaskException(use_message)
                    logger.debug('Found usage of "%s"', use_name)
                    unit_id = FortranUnitID(scope[0][1], reader.filename)
                    state.add_fortran_dependency(unit_id, use_name)
                    new_artifact.add_dependency(use_name)
                continue

            block_match: Optional[Match] = self._scoping_pattern.match(line)
            if block_match:
                # Beware we want the value of a different group to the one we
                # check the presence of.
                #
                block_name: str = block_match.group(1) \
                                  and block_match.group(2).lower()
                block_nature: str = block_match.group(3).lower()
                logger.debug('Found %s called "%s"', block_nature, block_name)
                scope.append((block_nature, block_name))
                continue

            proc_match: Optional[Match] \
                = self._procedure_pattern.match(line)
            if proc_match:
                proc_nature = proc_match.group(1).lower()
                proc_name = proc_match.group(2).lower()
                logger.debug('Found %s called "%s"', proc_nature, proc_name)
                scope.append((proc_nature, proc_name))

                # Check for the procedure being symbol-bound to C
                cbind_match: Optional[Match] \
                    = self._cbind_pattern.match(line)
                if cbind_match:
                    cbind_name = cbind_match.group(2)
                    # The name keyword on the bind statement is optional.
                    # If it doesn't exist, the procedure name is used
                    if cbind_name is None:
                        cbind_name = proc_name
                    cbind_name = cbind_name.lower().strip("'\"")
                    logger.debug('Bound to C symbol "%s"', cbind_name)
                    # A bind within an interface block means this is
                    # exposure of a C-defined function to Fortran,
                    # otherwise it is going the other way (allowing C
                    # code to call the Fortran procedure)
                    if any([stype == "interface" for stype, _ in scope]):
                        # TODO: This is sort of hijacking the mechanism used
                        # for Fortran module dependencies, only using the
                        # symbol name. Longer term we probably need a more
                        # elegant solution
                        unit_id = FortranUnitID(scope[0][1], reader.filename)
                        state.add_fortran_dependency(unit_id, cbind_name)
                        new_artifact.add_dependency(cbind_name)
                    else:
                        # Add to the C database
                        symbol_id = CSymbolID(cbind_name, reader.filename)
                        cstate.add_c_symbol(symbol_id)
                        new_artifact.add_definition(cbind_name)
                continue

            cbind_match = self._cbind_pattern.match(line)
            if cbind_match:
                # This should be a line binding from C to a variable definition
                # (procedure binds are dealt with above)
                cbind_name = cbind_match.group(2)

                # The name keyword on the bind statement is optional.
                # If it doesn't exist, the Fortran variable name is used
                if cbind_name is None:
                    var_search = re.search(r'.*::\s*(\w+)', line)
                    if var_search:
                        cbind_name = var_search.group(1)
                    else:
                        cbind_message \
                            = 'failed to find variable name ' \
                              'on C bound variable'
                        raise TaskException(cbind_message)

                cbind_name = cbind_name.lower().strip("'\"")
                logger.debug('Found C bound variable called "%s"', cbind_name)

                # Add to the C database
                symbol_id = CSymbolID(cbind_name, reader.filename)
                cstate.add_c_symbol(symbol_id)
                new_artifact.add_definition(cbind_name)

            iface_match: Optional[Match] = self._interface_pattern.match(line)
            if iface_match:
                iface_name = iface_match.group(1) \
                             and iface_match.group(1).lower()
                logger.debug('Found interface called "%s"', iface_name)
                scope.append(('interface', iface_name))
                continue

            type_match: Optional[Match] = self._type_pattern.match(line)
            if type_match:
                type_name = type_match.group(3).lower()
                logger.debug('Found type called "%s"', type_name)
                scope.append(('type', type_name))
                continue

            end_match: Optional[Match] = self._end_block_pattern.match(line)
            if end_match:
                end_nature: str = end_match.group(1) \
                    and end_match.group(1).lower()
                end_name: str = end_match.group(2) \
                    and end_match.group(2).lower()
                logger.debug('Found end of %s called %s',
                             end_nature, end_name)
                exp: Tuple[str, str] = scope.pop()

                if end_nature is not None:
                    if end_nature != exp[0]:
                        end_message = 'Expected end of {exp} "{name}" ' \
                                      'but found {found}'
                        end_values = {'exp': exp[0],
                                      'name': exp[1],
                                      'found': end_nature}
                        raise TaskException(
                            end_message.format(**end_values))
                if end_name is not None:
                    if end_name != exp[1]:
                        end_message = 'Expected end of {exp} "{name}" ' \
                                      'but found end of {found}'
                        end_values = {'exp': exp[0],
                                      'name': exp[1],
                                      'found': end_name}
                        raise TaskException(
                            end_message.format(**end_values))

        return [new_artifact]


class FortranPreProcessor(Task):
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
            msg = ('Fortran Preprocessor expects only one Artifact, '
                   f'but was given {len(artifacts)}')
            raise TaskException(msg)

        command = [self._preprocessor]
        command.extend(self._flags)
        command.append(str(artifact.location))

        output_file = (self._workspace /
                       artifact.location.with_suffix('.f90').name)
        command.append(str(output_file))

        logger.debug('Running command: ' + ' '.join(command))
        subprocess.run(command, check=True)

        return [Artifact(output_file,
                         artifact.filetype,
                         Raw)]


class FortranCompiler(Task):

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
            msg = ('Fortran Compiler expects only one Artifact, '
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
