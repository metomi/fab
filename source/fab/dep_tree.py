##############################################################################
# (c) Crown copyright Met Office. All rights reserved.
# For further details please refer to the file COPYRIGHT
# which you should have received as part of this distribution
##############################################################################
"""
Classes and helper functions related to the dependency tree, as created by the analysis stage.

"""

# todo: we've since adopted the term "source tree", so we should probably rename this module to match.

import logging
from pathlib import Path
from typing import Set, Dict, Iterable

logger = logging.getLogger(__name__)


class AnalysedFile(object):
    """
    An analysis result for a single file, containing symbol definitions and dependencies.

    File dependencies are set after construction.

    The object can represent itself as a dict for use with a csv.DictWriter.

    """
    def __init__(self, fpath: Path, file_hash, symbol_deps=None, symbol_defs=None, file_deps=None,
                 mo_commented_file_deps=None):
        """
        :param fpath:
            The source file that was analysed.
        :param file_hash:
            The hash of the source.
        :param symbol_defs:
            Set of symbol names defined by this source file.
        :param symbol_deps:
            Set of symbol names used by this source file.
            Can include symbols in the same file.
        :param file_deps:
            Other files on which this source depends. Must not include itself.
        :param mo_commented_file_deps:
            A set of C file names, without paths, on which this file depends.
            Comes from "DEPENDS ON:" comments which end in ".o".

        """
        self.fpath = fpath
        self.file_hash = file_hash
        self.symbol_defs: Set[str] = symbol_defs or set()
        self.symbol_deps: Set[str] = symbol_deps or set()
        self.file_deps: Set[Path] = file_deps or set()

        # dependencies from Met Office "DEPENDS ON:" code comments which refer to a c file
        self.mo_commented_file_deps: Set[str] = mo_commented_file_deps or set()

        assert all([d and len(d) for d in self.symbol_defs]), "bad symbol definitions"
        assert all([d and len(d) for d in self.symbol_deps]), "bad symbol dependencies"

    def add_symbol_def(self, name):
        assert name and len(name)
        self.symbol_defs.add(name.lower())

    def add_symbol_dep(self, name):
        assert name and len(name)
        self.symbol_deps.add(name.lower())

    def add_file_dep(self, name):
        assert name and len(name)
        self.file_deps.add(name)

    def __str__(self):
        return f"AnalysedFile {self.fpath} {self.file_hash} {self.symbol_defs} {self.symbol_deps} {self.file_deps}"

    def __eq__(self, other):
        return (
                self.fpath == other.fpath and
                self.file_hash == other.file_hash and
                self.symbol_defs == other.symbol_defs and
                self.symbol_deps == other.symbol_deps and
                self.file_deps == other.file_deps and
                self.mo_commented_file_deps == other.mo_commented_file_deps
        )

    def __hash__(self):
        return hash((
            self.fpath,
            self.file_hash,
            tuple(sorted(self.symbol_defs)),
            tuple(sorted(self.symbol_deps)),
            tuple(sorted(self.file_deps)),
            tuple(sorted(self.mo_commented_file_deps)),
        ))

    #
    # this stuff is for reading and writing with a csv.DictWriter
    #

    @classmethod
    def field_names(cls):
        return ['fpath', 'file_hash', 'symbol_defs', 'symbol_deps', 'file_deps', 'mo_commented_file_deps']

    def as_dict(self):
        """Serialise"""
        return {
            "fpath": self.fpath,
            "file_hash": self.file_hash,
            "symbol_deps": ';'.join(self.symbol_deps),
            "symbol_defs": ';'.join(self.symbol_defs),
            "file_deps": ';'.join(map(str, self.file_deps)),
            "mo_commented_file_deps": ';'.join(self.mo_commented_file_deps),
        }

    @classmethod
    def from_dict(cls, d):
        """Deserialise"""
        return cls(
            fpath=Path(d["fpath"]),
            file_hash=int(d["file_hash"]),
            symbol_deps=set(d["symbol_deps"].split(';')) if d["symbol_deps"] else set(),
            symbol_defs=set(d["symbol_defs"].split(';')) if d["symbol_defs"] else set(),
            file_deps=set(map(Path, d["file_deps"].split(';'))) if d["file_deps"] else set(),
            mo_commented_file_deps=set(d["mo_commented_file_deps"].split(';')) if d["mo_commented_file_deps"] else set()
        )


# Possibly overkill to have a class for this, but it makes analysis code simpler via type filtering.
class EmptySourceFile(object):
    """
    An analysis result for a file which resulted in an empty parse tree.

    """
    def __init__(self, fpath: Path):
        self.fpath = fpath


def extract_sub_tree(source_tree: Dict[Path, AnalysedFile], root: Path, verbose=False) -> Dict[Path, AnalysedFile]:
    """
    Extract the subtree required to build the target, from the full source tree of all analysed source files.
    
    :param source_tree:
        The source tree of analysed files.
    :param root:
        The root of the dependency tree, this is the filename containing the Fortran program.
    :param verbose:
        Log missing dependencies.

    """
    result: Dict[Path, AnalysedFile] = dict()
    missing: Set[Path] = set()

    _extract_sub_tree(src_tree=source_tree, key=root, dst_tree=result, missing=missing, verbose=verbose)

    if missing:
        logger.warning(f"{root} has missing deps: {missing}")

    return result


def _extract_sub_tree(src_tree: Dict[Path, AnalysedFile], key: Path,
                      dst_tree: Dict[Path, AnalysedFile], missing: Set[Path], verbose: bool, indent: int = 0):
    # is this node already in the sub tree?
    if key in dst_tree:
        return

    if verbose:
        logger.debug("----" * indent + str(key))

    # add it to the output tree
    node = src_tree[key]
    assert node.fpath == key, "tree corrupted"
    dst_tree[key] = node

    # add its child deps
    for file_dep in node.file_deps:

        # one of its deps is missing!
        if not src_tree.get(file_dep):
            if logger and verbose:
                logger.debug("----" * indent + " !!MISSING!! " + str(file_dep))
            missing.add(file_dep)
            continue

        # add this child dep
        _extract_sub_tree(
            src_tree=src_tree, key=file_dep, dst_tree=dst_tree, missing=missing, verbose=verbose, indent=indent + 1)


def add_mo_commented_file_deps(source_tree: Dict[Path, AnalysedFile]):
    """
    Handle dependencies from Met Office "DEPENDS ON:" code comments which refer to a c file.
    These are the comments which refer to a .o file and not those which just refer to symbols.
    
    :param source_tree:
        The source tree of analysed files.

    """
    analysed_fortran = filter_source_tree(source_tree, '.f90')
    analysed_c = filter_source_tree(source_tree, '.c')

    lookup = {c.fpath.name: c for c in analysed_c}
    num_found = 0
    for f in analysed_fortran:
        num_found += len(f.mo_commented_file_deps)
        for dep in f.mo_commented_file_deps:
            f.file_deps.add(lookup[dep].fpath)
    logger.info(f"processed {num_found} DEPENDS ON file dependencies")


def filter_source_tree(source_tree: Dict[Path, AnalysedFile], suffixes: Iterable[str]):
    """
    Pull out files with the given extensions from a source tree.

    Returns a list of :class:`~fab.dep_tree.AnalysedFile`.

    :param source_tree:
        The source tree of analysed files.
    :param suffixes:
        The suffixes we want, including the dot.

    """
    all_files: Iterable[AnalysedFile] = source_tree.values()
    return [af for af in all_files if af.fpath.suffix in suffixes]


def validate_dependencies(source_tree):
    """
    If any dep is missing from the tree, then it's unknown code and we won't be able to compile.

    :param source_tree:
        The source tree of analysed files.

    """
    missing = set()
    for f in source_tree.values():
        missing.update([str(file_dep) for file_dep in f.file_deps if file_dep not in source_tree])

    if missing:
        logger.error(f"Unknown dependencies, expecting build to fail: {', '.join(sorted(missing))}")
