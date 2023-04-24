.. Fab documentation master file, created by
   sphinx-quickstart on Mon Jan 24 17:04:51 2022.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to Fab's documentation!
*******************************
Version |version| (release |release|).

What is fab?
============

An open source build system for Fortran and C projects.
Initially designed to build the Met Office's major scientific applications, LFRic and the UM.

Why a New Build Tool?
=====================

There are several existing build tools, such as Make, and many more build system
builders such as CMake out there. So why muddy these already turgid waters?

A number of popular solutions to the problem of building software were examined and
it became apparent that there was a fundamental mismatch in requirements.

Most build systems are designed from the position that the executable is the product. The
source files needed to create that executable are listed because they change infrequently
and are merely a means to the end of creating an executable.

Scientific software can be rather different. In this paradigm the source is the product and
the executable merely a handy means to access it's power. When building is viewed from
this point-of-view maintaining lists of source is restricting because it changes so often.

In this light it makes sense to develop a new build tool which gives primacy to the source
rather than the executable. The ultimate goal is to support science developers in their
work.

For more, please see the :ref:`features<Features>` page.

Running fab
===========
* how to :ref:`set up an environment<Environment>`
* how to :ref:`install fab<Install>`

Zero config
-----------
To run fab with :ref:`zero configuration<Zero Config>`, type ``fab`` at the command line, within your project.

.. code-block:: console

   $ cd /path/to/your/source
   $ fab

The executable file can be found in the :ref:`Fab Workspace<Configure Fab Workspace>`.


Config files
------------
* intro to :ref:`config files<Config Intro>`
* guide to :ref:`writing config files<Writing Config>`
* :ref:`advanced config<Advanced Config>`

See also
========
* `Project wiki <https://github.com/metomi/fab/wiki>`_
* `Fab on PyPI <https://pypi.org/project/sci-fab/>`_
* `Fab on Github <https://github.com/metomi/fab>`_
* :ref:`Developers guide<Development>`




.. toctree::
   :maxdepth: 2
   :caption: Contents:
   :hidden:

   install
   environment
   metoffice
   config_intro
   writing_config
   advanced_config
   features
   Api Reference <apidoc/modules>
   development
   glossary
   genindex
   py-modindex
