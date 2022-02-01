"""
Fortran file compilation.

"""
import logging
from pathlib import Path
from string import Template
from typing import List, Set

from fab.constants import BUILD_SOURCE, BUILD_OUTPUT

from fab.config import FlagsConfig, AddPathFlags
from fab.dep_tree import AnalysedFile, by_type

from fab.steps import Step
from fab.util import CompiledFile, log_or_dot_finish, log_or_dot, run_command

logger = logging.getLogger('fab')


class CompileFortran(Step):

    def __init__(self, compiler: List[str], common_flags=None, path_flags=None, name='compile fortran'):
        super().__init__(name)
        path_flags = path_flags or []

        # todo: template and config duplication, make a superclass, like RunExe?
        substitute = dict(source=self.workspace/BUILD_SOURCE, output=self.workspace/BUILD_OUTPUT)
        self._compiler = [Template(i).substitute(substitute) for i in compiler]

        self._flags = FlagsConfig(
            common_flags=common_flags,
            all_path_flags=[AddPathFlags(path_filter=i[0], flags=i[1]) for i in path_flags]
        )

    def run(self, artefacts):
        """
        Compiles all Fortran files in the *build_tree* artefact, creating the *compiled_c* artefact.

        This step uses multiprocessing, unless disabled in the :class:`~fab.steps.Step` class.

        """
        to_compile: Set[AnalysedFile] = {
            analysed_file for analysed_file in artefacts['build_tree'].values() if analysed_file.fpath.suffix == ".f90"}
        logger.info(f"\ncompiling {len(to_compile)} fortran files")

        all_compiled: List[CompiledFile] = []  # todo: use set?
        already_compiled_files: Set[Path] = set([])  # a quick lookup

        per_pass = []
        while to_compile:

            compile_next = self.get_compile_next(already_compiled_files, to_compile)

            logger.info(f"\ncompiling {len(compile_next)} of {len(to_compile)} remaining files")
            results_this_pass = self.run_mp(items=compile_next, func=self.compile_file)

            # any errors?
            # todo: improve by_type pattern to handle all exceptions as one
            errors = []
            for i in results_this_pass:
                if isinstance(i, Exception):
                    errors.append(i)
            if len(errors):
                logger.error(f"\nThere were {len(errors)} compile errors this pass\n\n")
            if errors:
                # todo: do we need to fail if we're building a library? might not need that broken file...
                err_str = "\n\n".join(map(str, errors))
                raise RuntimeError(f"Error in compiling pass: {err_str}")

            # check what we did compile
            compiled_this_pass: Set[CompiledFile] = by_type(results_this_pass)[CompiledFile]
            per_pass.append(len(compiled_this_pass))
            if len(compiled_this_pass) == 0:
                logger.error("nothing compiled this pass")
                break

            # remove compiled files from list
            logger.debug(f"compiled {len(compiled_this_pass)} files")

            # results are not the same instances as passed in, due to mp copying
            compiled_fpaths = {i.analysed_file.fpath for i in compiled_this_pass}
            all_compiled.extend(compiled_this_pass)
            already_compiled_files.update(compiled_fpaths)

            # remove from remaining to compile
            to_compile = set(filter(lambda af: af.fpath not in compiled_fpaths, to_compile))

        log_or_dot_finish(logger)
        logger.debug(f"compiled per pass {per_pass}")
        logger.info(f"total fortran compiled {sum(per_pass)}")

        if to_compile:
            logger.debug(f"there were still {len(to_compile)} files left to compile")
            for af in to_compile:
                logger.debug(af.fpath)
            logger.error(f"there were still {len(to_compile)} files left to compile")
            exit(1)

        artefacts['compiled_fortran'] = all_compiled

    def get_compile_next(self, already_compiled_files: Set[Path], to_compile: Set[AnalysedFile]):

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

        # unable to compile anything?
        if len(to_compile) and not compile_next:
            all_unfulfilled = set()
            for unfulfilled in not_ready.values():
                all_unfulfilled = all_unfulfilled.union(unfulfilled)
            raise RuntimeError(f"Nothing more can be compiled due to unfulfilled dependencies: {', '.join(map(str, all_unfulfilled))}")

        return compile_next

    def compile_file(self, analysed_file: AnalysedFile):
        command = [*self._compiler]
        command.extend(self._flags.flags_for_path(analysed_file.fpath))
        command.append(str(analysed_file.fpath))

        output_fpath = analysed_file.fpath.with_suffix('.o')
        if self.debug_skip and output_fpath.exists():
            log_or_dot(logger, f'Compiler skipping: {output_fpath}')
            return CompiledFile(analysed_file, output_fpath)

        command.extend(['-o', str(output_fpath)])

        log_or_dot(logger, 'Compiler running command: ' + ' '.join(command))
        try:
            run_command(command)
        except Exception as err:
            return Exception("Error calling compiler:", err)

        return CompiledFile(analysed_file, output_fpath)
