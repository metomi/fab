! (c) Crown copyright Met Office. All rights reserved.
! For further details please refer to the file COPYRIGHT
! which you should have received as part of this distribution
MODULE f_var

USE, INTRINSIC :: ISO_C_BINDING

IMPLICIT NONE
PRIVATE

CHARACTER(kind=c_char, len=1), &
  DIMENSION(12), BIND(c), TARGET, SAVE :: &
    helloworld=['H','e','L','l','O',' ','w','O','r','L','d','?']

END MODULE f_var
