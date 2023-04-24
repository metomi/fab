.. _Environment:

Environment
***********

Fab requires a suitible Python environment in which to run. This page outlines
some routes to achieving such an environment.

This page contains general instructions, there are additional instructions for
:ref:`Met Office<MetOffice>` users elsewhere.


.. _Requirements:

Requirements
============

The minimum dependencies for Fab to build a project are:

* Python >= 3.7
* fParser >= 0.16.0
* Fortran compiler
* Linker

If you intend to compile C you will need a C compiler and linker but also:

* libclang
* python-clang

If you want pretty charts to be plotted from the build metrics you will need:

* matplotlib


Obtaining Fab
=============

Although you can install the tool from a copy of the `source`_ it is usually
preferable to use one of the managed packages.

Packages are made available through `PyPI`_ and `Conda forge`_ and are installed
in the usual way for these services. Some examples follow.

.. _source: https://github.com/metomi/fab
.. _PyPI: https://pypi.org/project/sci-fab/
.. _Conda forge: https://anaconda.org/conda-forge/sci-fab


Somebody Elses Problem
----------------------

Some of the prerequisites may require system administrator intervention. If they
are feeling benevolent your administrator may even be prevailed upon to install
the whole lot.


Using a Python Virtual Environment
----------------------------------

A virtual environment is created in the normal way and `pip` used to install
Fab:

.. code-block:: console

    $ python -m venv $ENV_PATH
    $ . $ENV_PATH/bin/activate
    $ pip install sci-fab

Where `$ENV_PATH` is the location for the new environment.

If you want to compile C you will need to add the prerequisites for that:

.. code-block:: console

    $ pip install python-clang

Note that this requires a suitible `libclang` to be installed on your system
which may require system administrator internvention.

Finally, to get plots from the metrics you will need:

.. code-block:: console

    $ pip install matplotlib


.. _Anaconda:

Using Anaconda
--------------

Anaconda can be used in a similar way to the built in Python virtual
environemnt but can also handle your C needs:

.. code-block:: console

    $ conda create -n FabEnv sci-fab

Or you can add Fab to an existing environment:

.. code-block:: console

    $ conda install -n ExistingEnv sci-fab

If you want to compile C then you will need to add the prerequisites for that:

.. code-block:: console

    $ conda install -n FabEnv python-clang

And again, if you want to plot the build metrics:

.. code-block:: console

    $ conda install -n FabEnv matplotlib


Using Containers
----------------

The dockerfile in `envs/docker`_ can be used to create a suitible container for
running Fab:

.. code-block:: console

    $ docker build -t fab $FAB_WC/envs/docker
    $ docker run --env PYTHONPATH=/fab -v $FAB_WC/source:/fab -v /home/$USER:/home/$USER -it fab bash

This was tested on Windows, running Ubuntu in WSL but is not regularly tested
so can not be guaranteed.

.. _envs/docker: https://github.com/metomi/fab/tree/master/envs/docker
