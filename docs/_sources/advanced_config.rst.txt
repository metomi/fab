.. _Advanced Config:

Advanced Configuration
**********************

A lot can be achieved with simple configurations but some of the more esoteric
aspects of software building may require more esoteric Fab features.


.. _env_vars:

Understanding the Environment
=============================

Fab uses well-known environment variables to identify tools and configure them.


.. list-table:: Environment variables

   * - FPP
     - Fortran preprocessor, e.g ``fpp`` or ``cpp -traditional-cpp -P``.
       Fab imposes the ``-P``.
   * - FC
     - Fortran compiler, e.g ``gfortran`` or ``ifort -c``.
       Fab imposes the ``-c``.
   * - FFLAGS
     - Fortran compiler flags..
   * - CC
     - C compiler.
   * - CFLAGS
     - C compiler flags.
   * - LD
     - Linker, e.g ``ld``.
   * - LFLAGS
     - Linker flags.


Configuration Reuse
===================

If you find you have multiple build configurations with duplicated code, it
could be helpful to factor out the commonality into a shared module. Remember,
your build configuration is just a Python script at the end of the day.

In Fab's
`example configurations <https://github.com/metomi/fab/tree/master/run_configs>`_,
we have two build scripts to compile GCOM. Much of the configuration for these
two scripts is identical. We extracted the common steps into
`gcom_build_steps.py <https://github.com/metomi/fab/blob/master/run_configs/gcom/gcom_build_steps.py>`_
and used them in
`build_gcom_ar.py <https://github.com/metomi/fab/blob/master/run_configs/gcom/build_gcom_ar.py>`_
and
`build_gcom_so.py <https://github.com/metomi/fab/blob/master/run_configs/gcom/build_gcom_so.py>`_.


Separate grab and build scripts
===============================
If you are running many builds from the same source, you may wish to grab your
repo in a separate script and call it less frequently.

In this case your grab script might only contain a single step. You could
import your grab configuration to find out where it put the source.

.. code-block::
    :linenos:
    :caption: my_grab.py

    my_grab_config = BuildConfig(project_label='<project_label>')

    if __name__ == '__main__':
        with my_grab_config:
            fcm_export(my_grab_config, src='my_repo')


.. code-block::
    :linenos:
    :caption: my_build.py
    :emphasize-lines: 6

    from my_grab import my_grab_config


    if __name__ == '__main__':
        with BuildConfig(project_label='<project_label>') as state:
            grab_folder(state, src=grab_config.source_root),


Housekeeping
============

Fab will remove old files from the prebuilds folder. It will remove all prebuild files that are not part of the current build by default.

If you add a :func:`~fab.steps.cleanup_prebuilds.cleanup_prebuilds` step, you
can keep prebuild files for longer. This may be useful, for example, if you
often switch between two versions of your code and want to keep the prebuild
speed benefits when building both.


Sharing Prebuilds
=================

You can copy the contents of someone else's prebuilds folder into your own.

Fab uses hashes to keep track of the correct prebuilt files, and will find and
use them. There's also a helper step called
:func:`~fab.steps.grab.prebuild.grab_pre_build` you can add to your build
configurations.


PSyKAlight (PSyclone overrides)
===============================

If you need to override a PSyclone output file with a handcrafted version
you can use the ``overrides_folder`` argument to the
:func:`~fab.steps.psyclone.psyclone` step.

This specifies a normal folder containing source files. The step will delete
any files it creates if there's a matching filename in the overrides folder.


Two-Stage Compilation
=====================

The :func:`~fab.steps.compile_fortran.compile_fortran` step compiles files in
 passes, with each pass identifying all the files which can be compiled next,
 and compiling them in parallel.

Some projects have bottlenecks in their compile order, where lots of files are
stuck behind a single file which is slow to compile. Inspired by
`Busby <https://www.osti.gov/biblio/1393322>`_, Fab can perform two-stage
compilation where all the modules are built first in *fast passes* using the
`-fsyntax-only` flag, and then all the slower object compilation can follow in
a single pass.

The *potential* benefit is that the bottleneck is shortened, but there is a
tradeoff with having to run through all the files twice. Some compilers might
not have this capability.

Two-stage compilation is configured with the `two_stage_flag` argument to the
Fortran compiler.

.. code-block::
    :linenos:

    compile_fortran(state, two_stage_flag=True)


Managed arguments
=================

As noted above, Fab manages a few command line arguments for some of the tools
it uses.

Fortran Preprocessors
---------------------

Fab knows about some preprocessors which are used with Fortran, currently *fpp*
and *cpp*. It will ensure the ``-P`` flag is present to disable line numbering
directives in the output, which is currently required for fparser to parse the
output.

Fortran Compilers
-----------------

Fab knows about some Fortran compilers (currently *gfortran* or *ifort*).
It will make sure the `-c` flag is present to compile but not link.

If the compiler flag which sets the module folder is present, i.e. ``-J`` for
gfortran or ``-module`` for ifort, Fab will **remove** the flag, with a
notification, as it needs to use this flag to control the output location.


.. _Advanced Flags:

Tool arguments
============== 

Sometimes it is necessary to pass additional arguments when we call a software
tool.

Linker flags
------------

Probably the most common instance of the need to pass additional arguments is
to specify 3rd party libraries at the link stage.

.. code-block::
    :linenos:

    link_exe(state, flags=['-lm', '-lnetcdf'])

Path-specific flags
-------------------

For preprocessing and compilation, we sometimes need to specify flags
*per-file*. These steps accept both common flags and *path specific* flags.

.. code-block::
    :linenos:

    ...
    compile_fortran(
        common_flags=['-O2'],
        path_flags=[
            AddFlags('$output/um/*', ['-I' + '/gcom'])
        ],
    )

This will add ``-O2`` to every invocation of the tool, but only add the
``*/gcom*`` include path when processing files in the
``*<project workspace>/build_output/um*`` folder.

Path matching is done using Python's `fnmatch <https://docs.python.org/3.10/library/fnmatch.html#fnmatch.fnmatch>`_.
The ``$output`` is a template, see :class:`~fab.build_config.AddFlags`.

We can currently only *add* flags for a path.

.. note::
    This can require some understanding of where and when files are placed in
    the *build_output* folder: It will generally match the structure you've
    created in ``*<project workspace>/source*``, with your grab steps.
    
    Early steps like preprocessors generally read files from ``*source*`` and
    write to ``*build_output*``.
    
    Later steps like compilers generally read files which are already in
    ``*build_output*``.
    
    For more information on where files end up see :ref:`Directory Structure`.


.. _Directory Structure:

Folder Structure
================

It may be useful to understand how Fab uses the :term:`Project Workspace` and
in particular where it creates files within it.

.. code-block::

    <your $FAB_WORKSPACE>
       <project workspace>
          source/
          build_output/
             *.f90 (preprocessed Fortran files)
             *.mod (compiled module files)
             _prebuild/
                *.an (analysis results)
                *.o (compiled object files)
                *.mod (mod files)
          metrics/
          my_program.exe
          log.txt

The *project workspace* folder takes its name from the project label passed in to the build configuration.

The *source* folder is where grab steps place their files.

The *build_output* folder is where steps put their processed files.
For example, a preprocessor reads ``.F90`` from *source* and writes ``.f90`` to *build_output*.

The *_prebuild* folder contains reusable output. Files in this folder include a hash value in their filenames.

The *metrics* folder contains some useful stats and graphs. See :ref:`Metrics`.


.. _C Pragma Injector:

C Pragma Injector
=================

The C pragma injector creates new C files with ``.prag`` file extensions, in the
source folder. The C preprocessor looks for the output of this step by default.
If not found, it will fall back to looking for ``.c`` files in the source
listing.

.. code-block::
    :linenos:

    ...
    c_pragma_injector(state)
    preprocess_c(state)
    ...


.. _Custom Steps:

Custom Steps
============
If you need a custom build step, you can create a function with the @step
decorator.

Some example custom steps are included in the Fab testing configurations. For
example a simple example was created for building JULES.

The :func:`~fab.steps.root_inc_files.root_inc_files` step copies all ``.inc``
files in the source tree into the root of the source tree, to make subsequent
preprocessing flags easier to configure.

That is a simple example that doesn't need to interact with the
:term:`Artefact Store`. Sometimes inserting a custom step means inserting a new
:term:`Artefact Collection` into the flow of data between steps.

We can tell a subsequent step to read our new artefacts, instead of using it's
default :term:`Artefacts Getter`. We do this using the ``source`` argument,
which most Fab steps accept. (See :ref:`Overriding default collections`)

.. code-block::
    :linenos:

    @step
    def custom_step(state):
            state._artefact_store['custom_artefacts'] = do_something(state._artefact_store['step 1 artefacts'])


    with BuildConfig(project_label='<project label>') as state:
        fab_step1(state)
        custom_step(state)
        fab_step2(state, source=CollectionGetter('custom_artefacts'))


Steps have access to multiprocessing methods through the
:func:`~fab.steps.run_mp` helper function. This processes artefacts in parallel.

.. code-block::
    :linenos:

    @step
    def custom_step(state):
        input_files = artefact_store['custom_artefacts']
        results = run_mp(state, items=input_files, func=do_something)


.. _Overriding default collections:

Collection names
================

Most steps allow the collections they read from and write to to be changed.

Let's imagine we need to upgrade a build script, adding a custom step to
prepare our Fortran files for preprocessing.

.. code-block::
    :linenos:

    find_source_files(state)  # this was already here

    # instead of this
    # preprocess_fortran(state)

    # we now do this
    my_new_step(state, output_collection='my_new_collection')
    preprocess_fortran(state, source=CollectionGetter('my_new_collection'))

    analyse(state)  # this was already here


Parser Workarounds
==================

Sometimes the parser used by Fab to understand source code can be unable to
parse valid source files due to bugs or shortcomings. In order to still be able
to build such code a number of possible work-arounds are presented.

.. _Unrecognised Deps Workaround:

Unrecognised Dependencies
-------------------------

If a language parser is not able to recognise a dependency within a file,
then Fab won't know the dependency needs to be compiled.

For example, some versions of fparser don't recognise a call on a one-line if
statement.

We can manually add the dependency using the `unreferenced_deps` argument to
:func:`~fab.steps.analyse.analyse`.

Pass in the name of the called function. Fab will find the file containing this
symbol and add it, *and all its dependencies*, to every :term:`Build Tree`.

.. code-block::
    :linenos:

    ...
    analyse(state, root_symbol='my_prog', unreferenced_deps=['my_func'])
    ...

Unparsable Files
----------------

If a language parser is not able to process a file at all, then Fab won't know
about any of its symbols and dependencies. This can sometimes happen to *valid
code* which compilers *are* able to process, for example if the language parser
is still maturing and can't yet handle an uncommon syntax.

In this case we can manually give Fab the analysis results using the
`special_measure_analysis_results` argument to
:func:`~fab.steps.analyse.analyse`.

Pass in a list of :class:`~fab.parse.fortran.FortranParserWorkaround` objects,
one for every file that can't be parsed. Each object contains the symbol
definitions and dependencies found in one source file.

.. code-block::
    :linenos:

    ...
    analyse(
        config,
        root_symbol='my_prog',
        special_measure_analysis_results=[
            FortranParserWorkaround(
                fpath=Path(state.build_output / "path/to/file.f90"),
                module_defs={'my_mod'}, symbol_defs={'my_func'},
                module_deps={'other_mod'}, symbol_deps={'other_func'}),
        ])
    ...

In the above snippet we tell Fab that ``file.f90`` defines a module called
``my_mod`` and a function called ``my_func``, and depends on a module called
``other_mod`` and a function called ``other_func``.

Custom Step
^^^^^^^^^^^

An alternative approach for some problems is to write a custom step to modify
the source so that the language parser can process it. Here's a simple example,
based on a
`real workaround <https://github.com/metomi/fab/blob/216e00253ede22bfbcc2ee9b2e490d8c40421e5d/run_configs/um/build_um.py#L42-L65>`_
where the parser gets confused by a variable called `NameListFile`.

.. code-block::
    :linenos:

    @step
    def my_custom_code_fixes(state):
        fpath = state.source_root / 'path/to/file.F90'
        in = open(fpath, "rt").read()
        out = in.replace("NameListFile", "MyRenamedVariable")
        open(fpath, "wt").write(out)

    with BuildConfig(project_label='<project_label>') as state:
        # grab steps first
        my_custom_code_fixes(state)
        # find_source_files, preprocess, etc, afterwards

A more detailed treatment of :ref:`Custom Steps` is given elsewhere.
