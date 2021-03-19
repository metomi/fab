/* (c) Crown copyright Met Office. All rights reserved.
  For further details please refer to the file COPYRIGHT
  which you should have received as part of this distribution */
#include <stdio.h>
#include "f_var.h"

void get_f_var_ptr(void **ptr);

void get_f_var_ptr(void **ptr)
{
  char *x;
  *ptr = &helloworld;
  x=(char *)*ptr;
  printf("<%c%c",x[0],x[1]);
  printf("%c%c%c",x[2],x[3],x[4]);
  printf("%c%c%c",x[5],x[6],x[7]);
  printf("%c%c%c",x[8],x[9],x[10]);
  printf("%c>\n",x[11]);
}
