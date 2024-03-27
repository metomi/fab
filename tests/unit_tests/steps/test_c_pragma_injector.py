##############################################################################
# (c) Crown copyright Met Office. All rights reserved.
# For further details please refer to the file COPYRIGHT
# which you should have received as part of this distribution
##############################################################################
from pathlib import Path
from sys import version_info as sys_version_info
from textwrap import dedent

import pytest

from fab.steps.c_pragma_injector import inject_pragmas


class TestInjectPragmas(object):

    def test_vanilla(self, tmp_path: Path):
        input_file = tmp_path / 'vanilla.c'
        input_file.write_text(
            dedent(
                """
                // hi there, ignore me
                
                #include <foo>
                
                #include "bar.h"
                """
            )
        )

        result = inject_pragmas(input_file)
        output = ''.join(list(result))

        assert output == dedent("""
            // hi there, ignore me
            
            #pragma FAB SysIncludeStart
            #include <foo>
            #pragma FAB SysIncludeEnd
            
            #pragma FAB UsrIncludeStart
            #include "bar.h"
            #pragma FAB UsrIncludeEnd
            """)

    def test_another(self, tmp_path: Path):
        input_file = tmp_path / 'more_elaborate.c'
        input_file.write_text(
            dedent(
                """
               #include "user_include.h"
               Unrelated text
               #include 'another_user_include.h'
               #include <system_include.h>
               More unrelated text
               #include <another_system_include.h>
                """
            )
        )

        result = inject_pragmas(input_file)
        output = ''.join(list(result))

        assert output == dedent(
            """
           #pragma FAB UsrIncludeStart
           #include "user_include.h"
           #pragma FAB UsrIncludeEnd
           Unrelated text
           #pragma FAB UsrIncludeStart
           #include 'another_user_include.h'
           #pragma FAB UsrIncludeEnd
           #pragma FAB SysIncludeStart
           #include <system_include.h>
           #pragma FAB SysIncludeEnd
           More unrelated text
           #pragma FAB SysIncludeStart
           #include <another_system_include.h>
           #pragma FAB SysIncludeEnd
            """
        )
