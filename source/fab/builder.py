##############################################################################
# (c) Crown copyright Met Office. All rights reserved.
# For further details please refer to the file COPYRIGHT
# which you should have received as part of this distribution
##############################################################################
import argparse
import configparser
import csv
import os
import warnings
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime
from time import perf_counter
from typing import Dict, List, Tuple, Set, Iterable

import logging
import multiprocessing
from pathlib import Path, PosixPath
import shutil
import sys

from pip._internal.index.sources import build_source

from config_sketch import FlagsConfig
from fab.constants import BUILD_OUTPUT, SOURCE_ROOT, BUILD_SOURCE
from fab.database import SqliteStateDatabase
from fab.tasks import Task

from fab.tasks.common import Linker, HeaderAnalyser
from fab.tasks.fortran import \
    FortranAnalyser, \
    FortranCompiler
from fab.tasks.c import \
    CPreProcessor, \
    CAnalyser, \
    CCompiler
from fab.dep_tree import AnalysedFile, by_type, extract_sub_tree, EmptySourceFile, add_mo_commented_file_deps
from fab.util import log_or_dot_finish, do_checksum, file_walk, HashedFile, \
    time_logger, CompiledFile, input_to_output_fpath

logger = logging.getLogger('fab')
# logger.addHandler(logging.StreamHandler(sys.stderr))


runtime_str = datetime.now().strftime("%Y%m%d_%H%M%S")


def read_config(conf_file):
    """
    Read the config file.

    Adds processed attributes from the lists:
     - skip_files
     - unreferenced_deps
     - include_paths

    Relative include paths are relative to the location of each file being processed.
    Absolute include paths (beginning with /) are relative to the workspace root.
    """
    config = configparser.ConfigParser(allow_no_value=True)
    config.read(conf_file)

    config.skip_files = []
    # todo: don't use walrus operator, and set the Python version to [3.6?] in env and setup.
    if skip_files_config := config['settings']['skip-files-list']:
        for line in open(skip_files_config, "rt"):
            config.skip_files.append(line.strip())

    config.unreferenced_deps = list(filter(
        lambda i: bool(i),
        [i.strip() for i in config['settings']['unreferenced-dependencies'].split(',')]))

    # config.src_paths = [Path(os.path.expanduser(i)) for i in config['settings']['src-paths'].split(',')]
    # config.include_paths = [Path(os.path.expanduser(i)) for i in config['settings']['include-paths'].split(',')]

    return config


def entry() -> None:
    """
    Entry point for the Fab build tool.
    """
    import fab

    description = 'Flexible build system for scientific software.'

    parser = argparse.ArgumentParser(add_help=False,
                                     description=description)
    # We add our own help so as to capture as many permutations of how people
    # might ask for help. The default only looks for a subset.
    parser.add_argument('-h', '-help', '--help', action='help',
                        help='Print this help and exit')
    parser.add_argument('-V', '--version', action='version',
                        version=fab.__version__,
                        help='Print version identifier and exit')
    parser.add_argument('-v', '--verbose', action='count', default=0,
                        help='Increase verbosity (may be specified once '
                             'for moderate and twice for debug verbosity)')
    parser.add_argument('-w', '--workspace', metavar='PATH', type=Path,
                        default=Path.cwd() / 'working',
                        help='Directory for working files.')
    parser.add_argument('--nprocs', action='store', type=int, default=2,
                        choices=range(2, multiprocessing.cpu_count()),
                        help='Provide number of processors available for use,'
                             'default is 2 if not set.')
    parser.add_argument('--skip-if-exists', action="store_true")
    # todo: this won't work with multiple source folders
    parser.add_argument('source', type=Path,
                        help='The path of the source tree to build. Accepts a comma separated list.')
    parser.add_argument('conf_file', type=Path, default='config.ini',
                        help='The path of the configuration file')
    arguments = parser.parse_args()

    verbosity_levels = [logging.WARNING, logging.INFO, logging.DEBUG]
    verbosity = min(arguments.verbose, 2)
    logger.setLevel(verbosity_levels[verbosity])

    config, skip_files, unreferenced_deps = read_config(arguments.conf_file)
    settings = config['settings']
    # flags = config['flags']

    # If not provided, name the exec after the target
    if settings['exec-name'] == '':
        settings['exec-name'] = settings['target']

    application = Fab(workspace=arguments.workspace,
                      target=settings['target'],
                      exec_name=settings['exec-name'],
                      fpp_flags=flags['fpp-flags'],
                      fc_flags=flags['fc-flags'],
                      ld_flags=flags['ld-flags'],
                      n_procs=arguments.nprocs,
                      skip_files=skip_files,
                      unreferenced_deps=unreferenced_deps)
    application.run(arguments.source.split(','))


class Fab(object):
    def __init__(self,
                 # include_paths: List[Path],
                 workspace: Path,
                 target: str,
                 exec_name: str,
                 cpp_flags: FlagsConfig,
                 fpp_flags: FlagsConfig,
                 fc_flags: FlagsConfig,
                 cc_flags: FlagsConfig,
                 ld_flags: str,
                 n_procs: int,
                 stop_on_error: bool = True,  # todo: i think we accidentally stopped using this
                 skip_files=None,
                 unreferenced_deps=None,
                 use_multiprocessing=True,
                 debug_skip=False,
                 dump_source_tree=False,
    ):

        # self.source_paths = source_paths
        self.n_procs = n_procs
        self.target = target
        self._workspace = workspace
        self.skip_files = skip_files or []
        self.fc_flags = fc_flags
        self.cc_flags = cc_flags
        self.unreferenced_deps: List[str] = unreferenced_deps or []
        self.use_multiprocessing = use_multiprocessing
        self.dump_source_tree = dump_source_tree
        # self.include_paths = include_paths or []

        if not workspace.exists():
            workspace.mkdir(parents=True)
        if not (workspace / BUILD_OUTPUT).exists():
            (workspace / BUILD_OUTPUT).mkdir()

        self._state = SqliteStateDatabase(workspace)

        # Initialise the required Tasks, providing them with any static
        # properties such as flags to use, workspace location etc
        # TODO: Eventually the tasks may instead access many of these
        # properties via the configuration (at Task runtime, to allow for
        # file-specific overrides?)
        # self.fortran_preprocessor = FortranPreProcessor(
        self.fortran_preprocessor = CPreProcessor(
            # preprocessor='cpp',
            preprocessor=['cpp', '-traditional-cpp', '-P'],
            flags=fpp_flags,
            workspace=workspace,
            output_suffix=".f90",
            debug_skip=debug_skip,
        )
        self.fortran_analyser = FortranAnalyser()

        self.fortran_compiler = FortranCompiler(
            # 'gfortran',
            # compiler=os.path.expanduser('~/.conda/envs/sci-fab/bin/gfortran'),
            # todo: make configurable
            compiler=[
                os.path.expanduser('~/.conda/envs/sci-fab/bin/gfortran'),
                '-c', '-J', str(workspace)
            ],

            # '/home/h02/bblay/.conda/envs/sci-fab/bin/mpifort',

            flags=self.fc_flags,
            # ['-std=gnu', '-c', '-J', str(self._workspace)] + self.fc_flags.split(),
            # ['-std=legacy', '-c', '-J', str(self._workspace)] + self.fc_flags.split(),

            # ['-std=f2003', '-c', '-J', str(self._workspace)] + self.fc_flags.split(),
            # ['-std=f2008', '-c', '-J', str(self._workspace)] + self.fc_flags.split(),
            # ['-std=f2008ts', '-c', '-J', str(self._workspace)] + self.fc_flags.split(),

            workspace=self._workspace
        )

        header_analyser = HeaderAnalyser(workspace)
        # self.c_pragma_injector = CPragmaInjector(workspace)
        self.c_preprocessor = CPreProcessor(
            preprocessor=['cpp'],
            flags=cpp_flags,
            workspace=workspace,
            debug_skip=debug_skip,
        )
        self.c_analyser = CAnalyser()
        self.c_compiler = CCompiler(
            compiler=['gcc', '-c', '-std=c99'],  # why std?
            # flags=['-c', '-std=c99'],
            flags=cc_flags,
            workspace=workspace,
        )

        # export OMPI_FC=gfortran
        # https://www.open-mpi.org/faq/?category=mpi-apps#general-build
        # steve thinks we might have to use mpif90
        self.linker = Linker(
            # 'gcc', ['-lc', '-lgfortran'] + ld_flags.split(),
            # 'mpifort', ['-lc', '-lgfortran'] + ld_flags.split(),

            '/home/h02/bblay/.conda/envs/sci-fab/bin/mpifort', ['-lc', '-lgfortran'] + ld_flags.split(),
            workspace, exec_name
        )

    def run(self):

        # todo: 23s on vdi
        # with time_logger("copying build tree"):
        #     self.copy_build_tree()

        with time_logger("walking build folder"):
            all_source = self.walk_build_source()

        # todo: replace with big include path?
        with time_logger("copying inc files to root"):
            self.copy_inc_files(all_source)

        # c_source_files = all_source[".c"]
        # with time_logger(f"adding pragmas to {len(c_source_files)} c source files"):
        #     pragmad_c = self.c_pragmas(c_source_files)

        c_source_files = all_source[".c"]
        with time_logger(f"preprocessing {len(c_source_files)} c files"):
            preprocessed_c = self.preprocess(fpaths=c_source_files, preprocessor=self.c_preprocessor)

        fortran_source_files = all_source[".F90"] + all_source[".f90"]
        with time_logger(f"preprocessing {len(fortran_source_files)} fortran source files"):
            preprocessed_fortran = self.preprocess(fpaths=fortran_source_files, preprocessor=self.fortran_preprocessor)

        # take hashes of all the files we preprocessed
        with time_logger(f"getting {len(preprocessed_fortran) + len(preprocessed_c)} file hashes"):
            preprocessed_hashes = self.get_latest_checksums(preprocessed_fortran | preprocessed_c)

        # analyse c and fortran
        with self.analysis_progress(preprocessed_hashes) as (unchanged, to_analyse, analysis_dict_writer):
            analysed_c, analysed_fortran = self.analyse(to_analyse, analysis_dict_writer)
        all_analysed_files: Dict[Path, AnalysedFile] = {a.fpath: a for a in unchanged + analysed_fortran + analysed_c}

        if self.dump_source_tree:
            with open(datetime.now().strftime(f"tmp/af1_{runtime_str}.txt"), "wt") as outfile:
                sorted_files = sorted(all_analysed_files.values(), key=lambda af: af.fpath)
                for af in sorted_files:
                    af.dump(outfile)

        # Make "external" symbol table
        with time_logger("creating symbol lookup"):
            symbols: Dict[str, Path] = self.gen_symbol_table(all_analysed_files)

        # turn symbol deps into file deps
        deps_not_found = set()
        with time_logger("converting symbol to file deps"):
            for analysed_file in all_analysed_files.values():
                for symbol_dep in analysed_file.symbol_deps:
                    # todo: does file_deps belong in there?
                    file_dep = symbols.get(symbol_dep)
                    if not file_dep:
                        deps_not_found.add(symbol_dep)
                        logger.debug(f"(might not matter) not found {symbol_dep} for {analysed_file}")
                        continue
                    analysed_file.file_deps.add(file_dep)
        if deps_not_found:
            logger.info(f"{len(deps_not_found)} deps not found")

        #  find the files for UM "DEPENDS ON:" commented file deps
        with time_logger("adding MO 'DEPENDS ON:' file dependency comments"):
            add_mo_commented_file_deps(analysed_fortran, analysed_c)

        if self.dump_source_tree:
            with open(datetime.now().strftime(f"tmp/af2_{runtime_str}.txt"), "wt") as outfile:
                sorted_files = sorted(all_analysed_files.values(), key=lambda af: af.fpath)
                for af in sorted_files:
                    af.dump(outfile)


        # TODO: document this: when there's duplicate symbols, the size of the (possibly wrong) build tree can vary...
        # Target tree extraction - for building executables.
        # When building library ".so" files, no target is needed.
        logger.info(f"source tree size {len(all_analysed_files)}")
        if self.target:
            with time_logger("extracting target tree"):
                build_tree = extract_sub_tree(all_analysed_files, symbols[self.target], verbose=False)
            logger.info(f"build tree size {len(build_tree)} (target '{symbols[self.target]}')")
        else:
            logger.info("no target specified, building everything")
            build_tree = all_analysed_files


        # Recursively add any unreferenced dependencies
        # (a fortran routine called without a use statement).
        # This is driven by the config list "unreferenced-dependencies"
        self.add_unreferenced_deps(symbols, all_analysed_files, build_tree)

        self.validate_build_tree(build_tree)

        # compile everything we need to build the target
        # todo: output into the folder structuresto avoid name clash
        with time_logger("compiling"):
            all_compiled = self.compile(build_tree)

        logger.info("\nlinking")
        self.linker.run(all_compiled)

        #
        # file_db = FileInfoDatabase(self._state)
        # for file_info in file_db:
        #     print(file_info.filename)
        #     # Where files are generated in the working directory
        #     # by third party tools, we cannot guarantee the hashes
        #     if file_info.filename.match(f'{self._workspace}/*'):
        #         print('    hash: --hidden-- (generated file)')
        #     else:
        #         print(f'    hash: {file_info.adler32}')
        #
        # fortran_db = FortranWorkingState(self._state)
        # for fortran_info in fortran_db:
        #     print(fortran_info.unit.name)
        #     print('    found in: ' + str(fortran_info.unit.found_in))
        #     print('    depends on: ' + str(fortran_info.depends_on))
        #
        # c_db = CWorkingState(self._state)
        # for c_info in c_db:
        #     print(c_info.symbol.name)
        #     print('    found_in: ' + str(c_info.symbol.found_in))
        #     print('    depends on: ' + str(c_info.depends_on))

    def analyse(self, to_analyse_by_type: Dict[str, List[HashedFile]], analysis_dict_writer: csv.DictWriter) \
            -> Tuple[List[AnalysedFile], List[AnalysedFile]]:

        fortran_files = to_analyse_by_type[".f90"]
        with time_logger(f"analysing {len(fortran_files)} preprocessed fortran files"):
            analysed_fortran, fortran_exceptions = self.analyse_file_type(
                fpaths=fortran_files, analyser=self.fortran_analyser.run, dict_writer=analysis_dict_writer)
        # did we find naughty fortran code?
        if self.fortran_analyser.depends_on_comment_found:
            warnings.warn("deprecated 'DEPENDS ON:' comment found in fortran code")

        c_files = to_analyse_by_type[".c"]
        with time_logger(f"analysing {len(c_files)} preprocessed c files"):
            analysed_c, c_exceptions = self.analyse_file_type(
                fpaths=c_files, analyser=self.c_analyser.run, dict_writer=analysis_dict_writer)

        # analysis errors?
        all_exceptions = fortran_exceptions | c_exceptions
        if all_exceptions:
            logger.error(f"{len(all_exceptions)} analysis errors")
            # exit(1)

        return analysed_c, analysed_fortran

    def gen_symbol_table(self, all_analysed_files: Dict[Path, AnalysedFile]):
        symbols = dict()
        duplicates = []
        for source_file in all_analysed_files.values():
            for symbol_def in source_file.symbol_defs:
                if symbol_def in symbols:
                    duplicates.append(ValueError(
                        f"duplicate symbol '{symbol_def}' defined in {source_file.fpath} "
                        f"already found in {symbols[symbol_def]}"))
                    continue
                symbols[symbol_def] = source_file.fpath

        if duplicates:
            err_msg = "\n".join(map(str, duplicates))
            logger.warning(f"Duplicates found while generating symbol table:\n{err_msg}")
            # exit(1)

        return symbols

    # def copy_build_tree(self):
    #     shutil.copytree(self._workspace / BUILD_SOURCE, self._workspace / BUILD_OUTPUT, dirs_exist_ok=True)

    def walk_build_source(self) -> Dict[str, List[Path]]:
        """
        Get all files in the folder and subfolders.

        Returns a dict[source_folder][extension] = file_list
        """
        build_source = self._workspace / BUILD_SOURCE
        fpaths = file_walk(build_source)
        if not fpaths:
            logger.warning(f"no source files found")
            exit(1)

        # group by suffix, and record folders
        fpaths_by_type = defaultdict(list)
        input_folders = set()
        for fpath in fpaths:
            fpaths_by_type[fpath.suffix].append(fpath)
            input_folders.add(fpath.parent.relative_to(build_source))

        # create output folders
        build_output = self._workspace / BUILD_OUTPUT
        for input_folder in input_folders:
            path = build_output / input_folder
            path.mkdir(parents=True, exist_ok=True)

        return fpaths_by_type

    # todo: multiprocessing
    # todo: ancillary file types should be in the project config?
    def copy_inc_files(self, files_by_type: Dict[str, List[Path]]):
        """
        Copy inc files into the workspace.

        Required for preprocessing
        Copies everything to the workspace root.
        Checks for name clash.

        """
        # inc files all go in the root - they're going to be removed altogether, soon
        inc_copied = set()
        for fpath in files_by_type[".inc"]:

            # don't copy form the output root to the output root!
            # (i.e ancillary files from a previous run)
            if fpath.parent == self._workspace / BUILD_OUTPUT:
                continue

            logger.debug(f"copying inc file {fpath}")
            if fpath.name in inc_copied:
                logger.error(f"name clash for ancillary file: {fpath}")
                exit(1)

            shutil.copy(fpath, self._workspace / BUILD_OUTPUT)
            inc_copied.add(fpath.name)

    # def c_pragmas(self, fpaths: List[Path]):
    #     if self.use_multiprocessing:
    #         with multiprocessing.Pool(self.n_procs) as p:
    #             results = p.map(CPragmaInjector, fpaths)
    #     else:
    #         results = [CPragmaInjector(f) for f in fpaths]
    #
    #     return results

    def preprocess(self, fpaths, preprocessor: Task) -> Set[Path]:
        if self.use_multiprocessing:
            with multiprocessing.Pool(self.n_procs) as p:
                results = p.map(preprocessor.run, fpaths)
        else:
            results = [preprocessor.run(f) for f in fpaths]
        results = by_type(results)

        # any errors?
        if results[Exception]:
            formatted_errors = "\n\n".join(map(str, results[Exception]))
            raise Exception(
                f"{formatted_errors}"
                f"\n\n{len(results[Exception])} "
                f"Error(s) found during preprocessing: "
            )

        log_or_dot_finish(logger)
        return results[PosixPath]

    def get_latest_checksums(self, fpaths: Iterable[Path]) -> Dict[Path, int]:
        if self.use_multiprocessing:
            with multiprocessing.Pool(self.n_procs) as p:
                results = p.map(do_checksum, fpaths)
        else:
            results = [do_checksum(f) for f in fpaths]

        latest_file_hashes: Dict[Path, int] = {fh.fpath: fh.file_hash for fh in results}
        return latest_file_hashes

    @contextmanager
    def analysis_progress(self, preprocessed_hashes) -> Tuple[List[AnalysedFile],
                                                              Dict[str, List[HashedFile]], csv.DictWriter]:
        """Open a new analysis progress file, populated with work already done in previous runs."""

        with time_logger("loading analysis results"):
            to_analyse, unchanged = self.load_analysis_results(preprocessed_hashes)

        with time_logger("starting analysis progress file"):
            unchanged_rows = (pu.as_dict() for pu in unchanged)
            analysis_progress_file = open(self._workspace / "__analysis.csv", "wt")
            analysis_dict_writer = csv.DictWriter(analysis_progress_file, fieldnames=AnalysedFile.field_names())
            analysis_dict_writer.writeheader()
            analysis_dict_writer.writerows(unchanged_rows)
            analysis_progress_file.flush()

        to_analyse_by_type: Dict[List[HashedFile]] = defaultdict(list)
        for hashed_file in to_analyse:
            to_analyse_by_type[hashed_file.fpath.suffix].append(hashed_file)

        yield unchanged, to_analyse_by_type, analysis_dict_writer

        analysis_progress_file.close()

    def load_analysis_results(self, latest_file_hashes) -> Tuple[List[HashedFile], List[AnalysedFile]]:
        # Load analysis results from previous run.
        # Includes the hash of the file when we last analysed it.
        # Note: it would be easy to switch to a database instead of a csv file
        prev_results: Dict[Path, AnalysedFile] = dict()
        try:
            with open(self._workspace / "__analysis.csv", "rt") as csv_file:
                dict_reader = csv.DictReader(csv_file)
                for row in dict_reader:
                    current_file = AnalysedFile.from_dict(row)

                    # file no longer there?
                    if current_file.fpath not in latest_file_hashes:
                        logger.info(f"a file has gone: {current_file.fpath}")
                        continue

                    # ok, we have previously analysed this file
                    prev_results[current_file.fpath] = current_file

            logger.info(f"loaded {len(prev_results)} previous analysis results")
        except FileNotFoundError:
            logger.info("no previous analysis results")
            pass

        # work out what needs to be reanalysed
        # unchanged: Set[ProgramUnit] = set()
        # to_analyse: Set[HashedFile] = set()
        unchanged: List[AnalysedFile] = []
        to_analyse: List[HashedFile] = []
        for latest_fpath, latest_hash in latest_file_hashes.items():
            # what happened last time we analysed this file?
            prev_pu = prev_results.get(latest_fpath)
            if (not prev_pu) or prev_pu.file_hash != latest_hash:
                # to_analyse.add(HashedFile(latest_fpath, latest_hash))
                to_analyse.append(HashedFile(latest_fpath, latest_hash))
            else:
                # unchanged.add(prev_pu)
                unchanged.append(prev_pu)
        logger.info(f"{len(unchanged)} already analysed, {len(to_analyse)} to analyse")
        # logger.debug(f"unchanged:\n{[u.fpath for u in unchanged]}")

        return to_analyse, unchanged

    # def start_recording_analysis_progress(self, unchanged: List[AnalysedFile]):
    #     # todo: use a database here? do a proper pros/cons with the wider team
    #     # start a new progress file containing anything that's still valid from the last run
    #     unchanged_rows = (pu.as_dict() for pu in unchanged)
    #     outfile = open(self._workspace / "__analysis.csv", "wt")
    #     dict_writer = csv.DictWriter(outfile, fieldnames=['name', 'fpath', 'deps', 'hash'])
    #     dict_writer.writeheader()
    #     dict_writer.writerows(unchanged_rows)
    #     outfile.flush()
    #     return outfile, dict_writer

    def analyse_file_type(self,
                          fpaths: List[HashedFile],
                          analyser,
                          dict_writer: csv.DictWriter) -> Tuple[List[AnalysedFile], Set[Exception]]:
        """
        Pass the files to the analyser and process the results.

        Returns a list of analysed files and a list of exceptions

        """
        # todo: return a set?
        new_program_units: List[AnalysedFile] = []
        exceptions = set()

        def iterate_results_DO_NOT_REFACTOR_AWAY(analysis_results):
            """
            WARNING: Do not pull this loop out into the code because we MUST iterate through the results
            from imap INSIDE the context manager - otherwise "something bad" happens...

            ..."something bad" seems to be that we jump out of the context before it gets a chance to
            create any workers, so the target function never runs and the iteration over results will hang.

            """
            for af in analysis_results:
                if isinstance(af, EmptySourceFile):
                    continue
                elif isinstance(af, Exception):
                    logger.error(f"\n{af}")
                    exceptions.add(af)
                elif isinstance(af, AnalysedFile):
                    new_program_units.append(af)
                    dict_writer.writerow(af.as_dict())
                else:
                    raise RuntimeError(f"Unexpected analysis result type: {af}")
            log_or_dot_finish(logger)

        if self.use_multiprocessing:
            with multiprocessing.Pool(self.n_procs) as p:
                # We use imap because we want to save progress as we go
                analysis_results = p.imap_unordered(analyser, fpaths)
                iterate_results_DO_NOT_REFACTOR_AWAY(analysis_results)
        else:
            analysis_results = (analyser(a) for a in fpaths)  # generator
            iterate_results_DO_NOT_REFACTOR_AWAY(analysis_results)

        return new_program_units, exceptions

    def add_unreferenced_deps(
            self, symbols: Dict[str, Path], all_analysed_files: Dict[Path, AnalysedFile],
            build_tree: Dict[Path, AnalysedFile]):
        """
        Add files to the target tree.

        """

        # todo: list those which are already found, e.g from the new comments deps

        if not self.unreferenced_deps:
            return
        logger.info(f"Adding {len(self.unreferenced_deps or [])} unreferenced dependencies")

        for symbol_dep in self.unreferenced_deps:

            # what file is the symbol in?
            analysed_fpath = symbols.get(symbol_dep)
            if not analysed_fpath:
                warnings.warn(f"no file found for unreferenced dependency {symbol_dep}")
                continue
            analysed_file = all_analysed_files[analysed_fpath]

            # was it found and analysed?
            if not analysed_file:
                warnings.warn(f"couldn't find file for symbol dep '{symbol_dep}'")
                continue

            # is it already in the build tree?
            if analysed_file.fpath in build_tree:
                logger.info(f"file {analysed_file.fpath} for unreferenced dependency {symbol_dep} "
                            f"is already in the build tree")
                continue

            # add it
            sub_tree = extract_sub_tree(src_tree=all_analysed_files, key=analysed_fpath)
            build_tree.update(sub_tree)

    def compile(self, build_tree):

        c_files: Set[AnalysedFile] = {af for af in build_tree.values() if af.fpath.suffix == ".c"}  # todo: filter?
        compiled_c = self.compile_c(c_files)

        fortran_files: Set[AnalysedFile] = {af for af in build_tree.values() if af.fpath.suffix == ".f90"}
        compiled_fortran = self.compile_fortran(fortran_files)

        all_compiled: Set[CompiledFile] = set(compiled_c + compiled_fortran)
        return all_compiled

    def compile_c(self, to_compile: Set[AnalysedFile]):
        logger.info(f"compiling {len(to_compile)} c files")
        if self.use_multiprocessing:
            with multiprocessing.Pool(self.n_procs) as p:
                results = p.map(self.c_compiler.run, to_compile)
        else:
            results = [self.c_compiler.run(c) for c in to_compile]

        errors = [result for result in results if isinstance(result, Exception)]
        if errors:
            err_msg = '\n\n'.join(map(str, errors))
            logger.error(f"There were {len(errors)} errors compiling {len(to_compile)} c files:\n{err_msg}")
            exit(1)

        compiled_c = [result for result in results if isinstance(result, CompiledFile)]
        logger.info(f"compiled {len(compiled_c)} c files")
        return compiled_c

    def compile_fortran(self, to_compile: Set[AnalysedFile]):
        logger.info(f"\ncompiling {len(to_compile)} fortran files")
        start = perf_counter()

        all_compiled = []  # todo: use set
        already_compiled_files = set()
        per_pass = []
        while to_compile:

            # find what to compile next
            compile_next = []
            not_ready = {}
            for af in to_compile:
                # all deps ready?
                unfulfilled = [dep for dep in af.file_deps if dep not in already_compiled_files and dep.suffix == '.f90']
                if not unfulfilled:
                    compile_next.append(af)
                else:
                    not_ready[af.fpath] = unfulfilled

            logger.info(f"\ncompiling {len(compile_next)} of {len(to_compile)} remaining files")

            # report if unable to compile everything
            if len(to_compile) and not compile_next:
                all_unfulfilled = set()
                for values in not_ready.values():
                    all_unfulfilled = all_unfulfilled.union(values)
                logger.error(f"All unfulfilled deps: {', '.join(map(str, all_unfulfilled))}")
                exit(1)

            if self.use_multiprocessing:
                with multiprocessing.Pool(self.n_procs) as p:
                    this_pass = p.map(self.fortran_compiler.run, compile_next)
            else:
                this_pass = [self.fortran_compiler.run(f) for f in compile_next]

            # any errors?
            # todo: improve by_type pattern to handle all exceptions as one
            errors = []
            for i in this_pass:
                if isinstance(i, Exception):
                    errors.append(i)
            if len(errors):
                logger.error(f"\nThere were {len(errors)} compile errors this pass\n\n")
            if errors:
                err_str = "\n\n".join(map(str, errors))
                logger.error(err_str)
                exit(1)

            # check what we did compile
            compiled_this_pass = by_type(this_pass)[CompiledFile]
            per_pass.append(len(compiled_this_pass))
            if len(compiled_this_pass) == 0:
                logger.error("nothing compiled this pass")
                break

            # remove compiled files from list
            logger.debug(f"compiled {len(compiled_this_pass)} files")

            # ProgramUnit - not the same as passed in, due to mp copying
            compiled_fpaths = {i.analysed_file.fpath for i in compiled_this_pass}
            # logger.debug(f"compiled_names {compiled_fpaths}")
            all_compiled.extend(compiled_this_pass)
            already_compiled_files.update(compiled_fpaths)

            # remove from remaining to compile
            to_compile = list(filter(lambda af: af.fpath not in compiled_fpaths, to_compile))

        log_or_dot_finish(logger)
        logger.debug(f"compiled per pass {per_pass}")
        logger.info(f"total compiled {sum(per_pass)}")
        logger.info(f"compilation took {perf_counter() - start}")

        if to_compile:
            logger.debug(f"there were still {len(to_compile)} files left to compile")
            for af in to_compile:
                logger.debug(af.fpath)
            logger.error(f"there were still {len(to_compile)} files left to compile")
            exit(1)

        return all_compiled

    def validate_build_tree(self, target_tree):
        """
        If any dep is not in the tree, then it's unknown code and we won't be able to compile.

        This was added as a helpful message when building the unreferenced dependencies list.
        """
        missing = set()
        for pu in target_tree.values():
            missing = missing.union(
                [str(file_dep) for file_dep in pu.file_deps if file_dep not in target_tree])

        if missing:
            logger.error(f"Unknown dependencies, expecting build to fail: {', '.join(sorted(missing))}")
            # exit(1)
