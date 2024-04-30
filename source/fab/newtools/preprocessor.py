##############################################################################
# (c) Crown copyright Met Office. All rights reserved.
# For further details please refer to the file COPYRIGHT
# which you should have received as part of this distribution
##############################################################################

"""This file contains the base class for any preprocessor, and two derived
classes for cpp and fpp.

"""

from pathlib import Path
from typing import List, Union

from fab.newtools.categories import Categories
from fab.newtools.tool import Tool


class Preprocessor(Tool):
    '''This is the base class for any preprocessor.
    '''

    def __init__(self, name: str, exec_name: str, category: Categories):
        super().__init__(name, exec_name, category)
        self._version = None

    def preprocess(self, input_file: Path, output_file: Path,
                   add_flags: Union[None, List[str]] = None):
        '''Calls the preprocessor to process the specified input file,
        creating the requested output file.
        :param input_file: input file.
        :param output_file: the output filename.
        :param add_flags: List with additional flags to be used.
        '''
        if add_flags:
            # Make a copy to avoid modifying the caller's list
            params = add_flags[:]
        else:
            params = []
        # Input and output files come as the last two parameters
        params.extend([str(input_file), str(output_file)])

        return self.run(additional_parameters=params)


# ============================================================================
class Cpp(Preprocessor):
    '''Class for cpp.
    '''
    def __init__(self):
        super().__init__("cpp", "cpp", Categories.C_PREPROCESSOR)


# ============================================================================
class CppFortran(Preprocessor):
    '''Class for cpp when used as a Fortran preprocessor
    '''
    def __init__(self):
        super().__init__("cpp", "cpp", Categories.FORTRAN_PREPROCESSOR)
        self.flags.extend(["-traditional-cpp", "-P"])


# ============================================================================
class Fpp(Preprocessor):
    '''Class for the Fortran-specific preprocessor.
    '''
    def __init__(self):
        super().__init__("fpp", "fpp", Categories.FORTRAN_PREPROCESSOR)
        # TODO: Proper check to be done
        self.is_available = False