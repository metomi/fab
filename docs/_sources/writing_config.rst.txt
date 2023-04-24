.. _Writing Config:


How to Write a Build Configuration
**********************************

This page walks through the process of writing a build script.

Configuration File
==================

Here's a simple configuration without any steps.

.. code-block::
    :linenos:
    :caption: build_it

    #!/usr/bin/env python3
    from logging import getLogger

    from fab.build_config import BuildConfig

    logger = getLogger('fab')

    if __name__ == '__main__':
        with BuildConfig(project_label='<project label>') as state:
            pass

If we want to run the build script from the command line,
we give it executable permission with the command ``chmod +x build_it``.
We also add the `shebang <https://en.wikipedia.org/wiki/Shebang_(Unix)>`_ directive on line 1,
telling our computer it's a Python script.

Pick a project label. Fab creates a :term:`project workspace` with this name.


Source Code
===========

Let's tell Fab where our source code is.

We use the :func:`~fab.steps.find_source_files.find_source_files` step for this.
We can point this step to a source folder, however, because Fab can sometimes
create artefacts alongside the source [1]_, we usually copy the source into the
project workspace first using a :mod:`~fab.steps.grab` step.

A grab step will copy files from a folder or remote repo into a folder called
"source" within the project workspace.

.. code-block::
    :linenos:
    :caption: build_it.py
    :emphasize-lines: 5,6,13,14

    #!/usr/bin/env python3
    from logging import getLogger

    from fab.build_config import BuildConfig
    from fab.steps.find_source_files import find_source_files
    from fab.steps.grab import GrabFolder

    logger = getLogger('fab')

    if __name__ == '__main__':

        with BuildConfig(project_label='<project label') as state:
            grab_folder(state, src='<path to source folder>')
            find_source_files(state)


.. note::
    Fab tries to minimise user input by providing *sensible defaults*.
    In this case, the user doesn't have to specify where the code goes.
    The grab and find_source_files steps already know what to do by default.
    Sensible defaults can be overridden.

Please see the documentation for :func:`~fab.steps.find_source_files.find_source_files` for more information,
including how to exclude certain source code from the build. More grab steps can be found in the :mod:`~fab.steps.grab`
module.

After the find_source_files step, there will be a collection called ``"all_source"``, in the artefact store.

.. [1] See :func:`~fab.steps.c_pragma_injector.c_pragma_injector` for an example of a step which
    creates artefacts in the source folder.


Preprocess
==========

Next we want to preprocess our source code.
Preprocessing resolves any `#include` and `#ifdef` directives in the code,
which must happen before we analyse it.

Steps generally create and find artefacts in the :term:`Artefact Store`, arranged into named collections.
The :func:`~fab.steps.preprocess.preprocess_fortran`
automatically looks for Fortran source code in a collection named `'all_source'`,
which is the default output from the preceding :funcfind_source_files step.
It filters just the (uppercase) ``.F90`` files.

.. note::

    Uppercase ``.F90`` are preprocessed into lowercase ``.f90``.

The Fortran preprocessor will read the :ref:`FPP<env_vars>` environment variable to determine which tool to call.


.. code-block::
    :linenos:
    :caption: build_it.py
    :emphasize-lines: 6,15

    #!/usr/bin/env python3
    from logging getLogger

    from fab.build_config import BuildConfig
    from fab.steps.find_source_files import find_source_files
    from fab.steps.preprocess import preprocess_fortran

    logger = getLogger('fab')

    if __name__ == '__main__':

        with BuildConfig(project_label='<project label') as state:
            grab_folder(state, src='<path to source folder>')
            find_source_files(state)
            preprocess_fortran(state)


Preprocessed files are created in the `'build_output'` folder, inside the project workspace.
After the fortran_preprocessor step, there will be a collection called ``"preprocessed_fortran"``, in the artefact store.


.. _Analyse Overview:

Analyse
=======

We must :func:`~fab.steps.analyse.analyse` the source code to determine which
Fortran files to compile, and in which order.

The Analyse step looks for source to analyse in several collections:

* ``.f90`` found in the source
* ``.F90`` we pre-processed into ``.f90``
* preprocessed c

.. code-block::
    :linenos:
    :caption: build_it.py
    :emphasize-lines: 4,18

    #!/usr/bin/env python3
    from logging import getLogger

    from fab.steps.analyse import analyse
    from fab.build_config import BuildConfig
    from fab.steps.find_source_files import find_source_files
    from fab.steps.grab import GrabFolder
    from fab.steps.preprocess import preprocess_fortran

    logger = getLogger('fab')

    if __name__ == '__main__':

        with BuildConfig(project_label='<project label') as state:
            grab_folder(state, src='<path to source folder>')
            find_source_files(state)
            preprocess_fortran(state)
            analyse(state, root_symbol='<program>')


Here we tell the analyser which :term:`Root Symbol` we want to build into an executable.
Alternatively, we can use the ``find_programs`` flag for Fab to discover and build all programs.

After the Analyse step, there will be a collection called ``"build_trees"``, in the artefact store.


Compile and Link
================

The :func:`~fab.steps.compile_fortran.compile_fortran` step compiles files in
the ``"build_trees"`` collection. The :func:`~fab.steps.link.link_exe` step
then creates the executable.

.. code-block::
    :linenos:
    :caption: build_it.py
    :emphasize-lines: 6,9,21,22

    #!/usr/bin/env python3
    from logging import getLogger

    from fab.steps.analyse import analyse
    from fab.build_config import BuildConfig
    from fab.steps.compile_fortran import compile_fortran
    from fab.steps.find_source_files import find_source_files
    from fab.steps.grab import GrabFolder
    from fab.steps.link import link_exe
    from fab.steps.preprocess import preprocess_fortran

    logger = logging.getLogger('fab')

    if __name__ == '__main__':

        with BuildConfig(project_label='<project label') as state:
            grab_folder(state, src='<path to source folder>')
            find_source_files(state)
            preprocess_fortran(state)
            analyse(state, root_symbol='<program>')
            compile_fortran(state)
            link_exe(state)


After the :func:`~fab.steps.link.link_exe` step, the executable name can be found in a collection called ``"executables"``.


Flags
=====

Preprocess, compile and link steps usually need configuration to specify
command-line arguments to the underlying tool, such as symbol definitions,
include paths, optimisation flags, etc. See also
:ref:`Advanced Flags<Advanced Flags>`.


C Code
======
Fab comes with C processing steps.
The :func:`~fab.steps.preprocess.preprocess_c` and :func:`~fab.steps.compile_c.compile_c` Steps
behave like their Fortran equivalents.

However preprocessing C currently requires a preceding step called the
:func:`~fab.steps.c_pragma_injector.c_pragma_injector`. This injects markers
into the C code so Fab is able to deduce which inclusions are user code and
which are system code. This allows system dependencies to be ignored.

See also :ref:`Advanced C Code<Advanced C Code>`


Further Reading
===============

More advanced configuration topics are discussed in
:ref:`Advanced Configuration`.

You can see more complicated configurations in the
`developer testing directory <https://github.com/metomi/fab/tree/master/run_configs>`_.
