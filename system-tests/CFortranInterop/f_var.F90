! (c) Crown copyright Met Office. All rights reserved.
! For further details please refer to the file COPYRIGHT
! which you should have received as part of this distribution
MODULE f_var

USE, INTRINSIC :: ISO_C_BINDING

IMPLICIT NONE
PRIVATE

CHARACTER(kind=c_char, LEN=20), BIND(c), TARGET, SAVE :: helloworld = 'HeLlO wOrLd?'

END MODULE f_var
