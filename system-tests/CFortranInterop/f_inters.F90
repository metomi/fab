! (c) Crown copyright Met Office. All rights reserved.
! For further details please refer to the file COPYRIGHT
! which you should have received as part of this distribution
MODULE f_inters

USE, INTRINSIC :: ISO_C_BINDING
USE, INTRINSIC :: ISO_FORTRAN_ENV

IMPLICIT NONE

INTERFACE
  SUBROUTINE string_me(string) BIND(c,name="get_f_var_ptr")
    IMPORT c_ptr
    IMPLICIT NONE
    TYPE(c_ptr), INTENT(IN OUT) :: string
  END SUBROUTINE
END INTERFACE

CONTAINS

SUBROUTINE set_string() BIND(c,name="f_inter")

IMPLICIT NONE

TYPE(c_ptr) :: str_ptr
CHARACTER(kind=c_char, len=20), POINTER :: f_char_pointer => NULL()

CALL string_me(str_ptr)
CALL C_F_POINTER(str_ptr, f_char_pointer)

f_char_pointer = "Hello World!"  // C_NULL_CHAR

write(OUTPUT_UNIT,'(A)') f_char_pointer

END SUBROUTINE set_string

END MODULE f_inters
