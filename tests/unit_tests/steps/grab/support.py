##############################################################################
# (c) Crown copyright Met Office. All rights reserved.
# For further details please refer to the file COPYRIGHT
# which you should have received as part of this distribution
##############################################################################
import filecmp
from pathlib import Path


class Workspace:
    def __init__(self, repo_path: Path, tree_path: Path):
        self.__repo_path = repo_path
        self.__tree_path = tree_path

    @property
    def repo_path(self) -> Path:
        return self.__repo_path

    @property
    def tree_path(self) -> Path:
        return self.__tree_path


def file_tree_compare(first: Path, second: Path) -> None:
    """
    Compare two file trees to ensure they are identical.
    """
    # Compare directory trees.
    #
    tree_comparison = filecmp.dircmp(str(first), str(second))
    assert len(tree_comparison.left_only) == 0
    assert len(tree_comparison.right_only) == 0

    # Compare files which exist in both trees.
    #
    _, mismatch, errors = filecmp.cmpfiles(str(first), str(second),
                                           tree_comparison.common_files,
                                           shallow=False)
    assert len(mismatch) == 0
    assert len(errors) == 0
