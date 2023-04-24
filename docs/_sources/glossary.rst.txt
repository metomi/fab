Glossary
********

.. glossary::

    Artefact
        *Artefact* is a term for an item, usually a file,
        created by a build step and added to the :term:`Artefact Store`.

        Some examples of artefacts are:
         - a Fortran file
         - a compiled object file
         - an executable file

        These exist as files in the file system and paths in the :term:`Artefact Store`.

    Artefact Collection
        A collection of :term:`Artefacts<Artefact>` in the :term:`Artefact Store`.

        These entries are usually a list of file paths or objects, sometimes a :term:`Source Tree`,
        but could be anything created by one step and consumed by another.

        As an example, a Fortran preprocessing step might create a list of output paths
        as ``artefact_store['preprocessed fortran'] = my_results``.
        A subsequent step could read this list.

    Artefacts Getter
        A helper class which a :term:`Step` uses to find artefacts in the :term:`Artefact Store`.
        Fab's built-in steps come with sensible defaults so the user doesn't have to write unnecessary config.

        As an example, the Fortran preprocessor has a default artefact getter which reads *".F90"* files
        from the :term:`Artefact Collection` called ``"all_source"``.

        Artefact getters are derived from :class:`~fab.artefacts.ArtefactsGetter`.

    Artefact Store
        The artefact store holds :term:`collections<Artefact Collection>` created and used by build steps.

        Fab passes the growing store to each step in turn,
        where they typically read a collection and create a new one for the next step.

    Build Tree
        A mapping of filenames to Analysis results.
        This subset of the :term:`Source Tree` contains only the files needed to build one target (:term:`Root Symbol`).
        It's created in the analysis step and used by the Fortran compilation step.
        When building a library, there is no root symbol and the entire source tree is included in a single build tree.

    Fab Workspace
        The folder in which all Fab output is created, for all build projects.
        Defaults to *~/fab-workspace*, and can be overridden by the ``$FAB_WORKSPACE`` environment variable
        or the `fab_workspace` argument to the :class:`~fab.build_config.BuildConfig` constructor.
        See also :ref:`Configure the Fab Workspace <Configure Fab Workspace>`

    Incremental Build
        This term refers to Fab's ability to avoid reprocessing an artefact if the output is already available.
        For example, if the user has previously built the project, there will likely be object files Fab can use
        to avoid recompilation.

    Prebuild
        This term has much overlap with the term :term:`Incremental Build`. It refers to artefacts that were built by
        another user, which can be copied to avoid reprocessing artefacts.
        Technical details on how this works can be found in :ref:`development:Incremental & Prebuilds`.

    Project Workspace
        A folder inside the :term:`Fab Workspace`, containing all source and output from a build config.

    Root Symbol
        The name of a Fortran PROGRAM, or ``"main"`` for C code. Fab builds an exe for every root symbol it's given.

    Source Tree
        The :class:`~fab.steps.analyse.analyse` step produces a dependency tree of the entire project source.
        This is represented as a mapping from Path to :class:`~fab.dep_tree.AnalysedDependent`.
        The AnalysedDependent's file dependencies are Paths, which refer to other entries in the mapping,
        and which define the tree structure. This is called the source tree.

    Step
        A step performs a function in the build process.

        Each step typically reads from, and adds to, an in-memory :term:`Artefact` repository called
        the :term:`Artefact Store`. Steps are derived from the :class:`~fab.steps.Step` base class.
