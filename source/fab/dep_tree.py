import logging
from collections import defaultdict
from pathlib import Path
from typing import Set, Dict, List, Tuple

logger = logging.getLogger(__name__)


# todo: might be better as a named tuple, as there's no methods
class AnalysedFile(object):

    def __init__(self, fpath: Path, file_hash, symbol_deps=None, symbol_defs=None, file_deps=None, mo_commented_file_deps=None):
        self.fpath = fpath
        self.file_hash = file_hash
        self.symbol_defs: Set[str] = symbol_defs or set()
        self.symbol_deps: Set[str] = symbol_deps or set()
        self.file_deps: Set[Path] = file_deps or set()

        # dependencies from Met Office "DEPENDS ON:" code comments which refer to a c file
        self.mo_commented_file_deps: Set[str] = mo_commented_file_deps or set()

        assert all([d and len(d) for d in self.symbol_defs]), "bad symbol definitions"
        assert all([d and len(d) for d in self.symbol_deps]), "bad symbol dependencies"
        # assert all([f and len(str(f)) for f in self.file_deps]), "bad file dependencies"

    def add_symbol_def(self, name):
        assert name and len(name)
        self.symbol_defs.add(name.lower())

    def add_symbol_dep(self, name):
        assert name and len(name)
        self.symbol_deps.add(name.lower())

    def add_file_dep(self, name):
        assert name and len(name)
        self.file_deps.add(name)

    def dump(self, outfile):
        outfile.write(f"{self.fpath} {self.file_hash}\n"
                      f"  symb defs: {sorted(self.symbol_defs)}\n"
                      f"  symb deps: {sorted(self.symbol_deps)}\n"
                      f"  file deps: {sorted(self.file_deps)}\n"
                      f"  modo deps: {sorted(self.mo_commented_file_deps)}\n")

    def __str__(self):
        return f"AnalysedFile {self.fpath} {self.file_hash} {self.symbol_defs} {self.symbol_deps} {self.file_deps}"

    def __eq__(self, other):
        return (
                self.fpath == other.fpath and
                self.file_hash == other.file_hash and
                self.symbol_defs == other.symbol_defs and
                self.symbol_deps == other.symbol_deps and
                self.file_deps == other.file_deps and
                self.mo_commented_file_deps == other.add_mo_commented_file_deps
        )

    def __hash__(self):
        return hash((
            self.fpath,
            self.file_hash,
            # todo: eww
            tuple(sorted(self.symbol_defs)),
            tuple(sorted(self.symbol_deps)),
            tuple(sorted(self.file_deps)),
            tuple(sorted(self.mo_commented_file_deps)),
        ))

    #
    # this stuff is for reading and writing
    #

    @classmethod
    def field_names(cls):
        return ['fpath', 'file_hash', 'symbol_defs', 'symbol_deps', 'file_deps', 'mo_commented_file_deps']

    # todo: poor name, and does it even belong in here?
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
            symbol_deps=d["symbol_deps"].split(';') if d["symbol_deps"] else [],
            symbol_defs=d["symbol_defs"].split(';') if d["symbol_defs"] else [],
            file_deps=map(Path, d["file_deps"].split(';')) if d["file_deps"] else [],
            mo_commented_file_deps=d["mo_commented_file_deps"].split(';') if d["mo_commented_file_deps"] else [],
        )


class EmptySourceFile(object):
    def __init__(self, fpath):
        self.fpath = fpath


def extract_sub_tree(
        src_tree: Dict[Path, AnalysedFile], key: Path, verbose=False) \
        -> Dict[Path, AnalysedFile]:
    """
    Extract a sub tree from a tree.

    Extracts a dict of program units, required to build the target,
    from the full dict of all program units.

    todo: better docstring
    """

    result = dict()
    missing = set()

    _extract_sub_tree(src_tree=src_tree, key=key, dst_tree=result, missing=missing, verbose=verbose)

    if missing:
        logger.warning(f"{key} has missing deps: {missing}")

    return result


def _extract_sub_tree(src_tree: Dict[Path, AnalysedFile], key: Path, dst_tree, missing, verbose, indent=0):

    # is this node already in the target tree?
    if key in dst_tree:
        return

    if verbose:
        logger.debug("----" * indent + str(key))

    # add it to the output tree
    node = src_tree[key]
    assert node.fpath == key
    dst_tree[key] = node

    # add its child deps
    for file_dep in node.file_deps:

        # one of its deps is missing!
        if not src_tree.get(file_dep):
            if logger and verbose:
                logger.debug("----" * indent + "!!!!" + str(file_dep))
            missing.add(file_dep)
            continue

        # add this child dep
        _extract_sub_tree(
            src_tree=src_tree, key=file_dep, dst_tree=dst_tree, missing=missing, verbose=verbose, indent=indent + 1)



# todo: don't leave this here
# TODO: This doesn't work with exceptions very well, yet
# todo: nasty surprise when sending in a list?
def by_type(iterable):
    result = defaultdict(set)
    for i in iterable:
        result[type(i)].add(i)
    return result


def add_mo_commented_file_deps(analysed_fortran: List[AnalysedFile], analysed_c: List[AnalysedFile]):
    """
    Handle dependencies from Met Office "DEPENDS ON:" code comments which refer to a c file.

    (These do not include "DEPENDS ON:" code comments which refer to symbols)
    """
    lookup = {c.fpath.name: c for c in analysed_c}
    num_found = 0
    for f in analysed_fortran:
        num_found += len(f.mo_commented_file_deps)
        for dep in f.mo_commented_file_deps:
            f.file_deps.add(lookup[dep])
    logger.info(f"processed {num_found} DEPENDS ON file dependencies")
