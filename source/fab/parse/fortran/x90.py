# ##############################################################################
#  (c) Crown copyright Met Office. All rights reserved.
#  For further details please refer to the file COPYRIGHT
#  which you should have received as part of this distribution
# ##############################################################################
from pathlib import Path
from typing import Union, Optional, Iterable, Dict, Any

from fparser.two.Fortran2003 import Use_Stmt, Call_Stmt, Name, Only_List, Actual_Arg_Spec_List, Part_Ref

from fab.parse import AnalysedFile
from fab.parse.fortran import FortranAnalyserBase, iter_content, logger, _typed_child
from fab.util import by_type


class AnalysedX90(AnalysedFile):
    """
    Analysis results for an x90 file.

    """
    def __init__(self, fpath: Union[str, Path], file_hash: int,
                 # todo: the fortran version doesn't include the remaining args - update this too, for simplicity.
                 kernel_deps: Optional[Iterable[str]] = None):
        """
        :param fpath:
            The path of the x90 file.
        :param file_hash:
            The checksum of the x90 file.

        todo: not as param

        :param kernel_deps:
            Kernel symbols used by the x90 file.

        """
        super().__init__(fpath=fpath, file_hash=file_hash)

        # Maps used kernel type symbols to the modules they're in
        self.kernel_deps: Dict[str, str] = kernel_deps or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fpath": str(self.fpath),
            "file_hash": self.file_hash,
            "kernel_deps": self.kernel_deps,
        }

    @classmethod
    def from_dict(cls, d):
        result = cls(
            fpath=Path(d["fpath"]),
            file_hash=d["file_hash"],
            kernel_deps=d["kernel_deps"],
        )
        assert result.file_hash is not None
        return result

    def __eq__(self, other):
        return vars(self) == vars(other)


class X90Analyser(FortranAnalyserBase):

    # Make a fortran compliant version so we can use fortran parsers on it.
    # Use hashing to reuse previous analysis results.

    def __init__(self):
        super().__init__(result_class=AnalysedX90)

    def walk_nodes(self, fpath, file_hash, node_tree) -> AnalysedX90:

        analysed_file = AnalysedX90(fpath=fpath, file_hash=file_hash)
        symbol_deps = {}

        for obj in iter_content(node_tree):
            obj_type = type(obj)
            try:
                if obj_type == Use_Stmt:
                    self._process_use_statement(symbol_deps, obj)  # raises

                elif obj_type == Call_Stmt:
                    self._process_call_statement(symbol_deps, analysed_file, obj)

            except Exception:
                logger.exception(f'error processing node {obj.item or obj_type} in {fpath}')

        # save results for reuse
        # analysis_fpath = self._get_analysis_fpath(fpath, file_hash)
        # analysed_file.save(analysis_fpath)

        return analysed_file

    def _process_use_statement(self, symbol_deps, obj):
        # Record the modules in which potential kernels live.
        # We'll find out if they're kernels later.
        module_dep = _typed_child(obj, Name, must_exist=True)
        only_list = _typed_child(obj, Only_List)
        if not only_list:
            return

        name_nodes = by_type(only_list.children, Name)
        for name in name_nodes:
            # self._symbol_deps[name.string] = module_dep.string
            symbol_deps[name.string] = module_dep.string

    def _process_call_statement(self, symbol_deps, analysed_file, obj):
        # if we're calling invoke, record the names of the args.
        # sanity check they end with "_type".
        called_name = _typed_child(obj, Name)
        if called_name.string == "invoke":
            arg_list = _typed_child(obj, Actual_Arg_Spec_List)
            if not arg_list:
                logger.info(f'No arg list passed to invoke: {obj.string}')
                return
            args = by_type(arg_list.children, Part_Ref)
            for arg in args:
                arg_name = _typed_child(arg, Name)
                arg_name = arg_name.string
                if arg_name in symbol_deps:
                    in_mod = symbol_deps[arg_name]
                    analysed_file.kernel_deps[arg_name] = in_mod
                else:
                    print(f"arg '{arg_name}' to invoke() was not used, presumed built-in kernel")