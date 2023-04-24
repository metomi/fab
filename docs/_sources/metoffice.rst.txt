.. _MetOfficeUsage:

Using Fab at the Met Office
===========================

For users working on Met Office desktop systems the following instructions may
prove useful.

Using Fab
~~~~~~~~~

If you just want to use Fab to build your source then there are a number of
fairly simple approaches.


Fortran Only
------------

If you don't need to build C, you can use the modules in the "extra
software" collection:

.. code-block:: console

    $ module use $EXTRA_SOFTWARE_MODULE_DIR
    $ module load python/3.7.0 support/fparser/0.0.16/python/3.7.0 fab/1.0.0/python/3.7.0

The Science I.T. group can provide the `EXTRA_SOFTWARE` path.

With the "fab" module loaded the `fab` command will be available and Fab based
build scripts will function.


Fortran and C
-------------

If you need to build C, or you use conda environments anyway you can use the
:ref:`Conda<Anaconda>` route to Fab-ulousness.

You will need to authenticate with Artifactory the first time you use Conda.
There is information regarding this on MetNet or ask Science I.T.


.. _Run Singularity:

Singularity Container
---------------------

You can run Fab in a singularity container as follows::

    singularity run oras://$URL/metomi/fab/MyImage:latest

The necessary URL is that normally used with singularity. Ask Science I.T. for
details.

If you need to use git from within the container, you'll need to set a couple of environment variables first::

    $ export SINGULARITY_BIND="/etc/pki/ca-trust/extracted/pem:/pem"
    $ export SINGULARITYENV_GIT_SSL_CAPATH="/pem"
    $ singularity shell oras://$URL/fab/MyImage:latest

See also :ref:`Instructions for building the image<Build Singularity>`.


Developing Fab
~~~~~~~~~~~~~~

If you want to develop Fab then there are some additional steps which may be
needed.


Mixing Virtual Environment and Environment Modules
--------------------------------------------------

If you prefer to use the built-in Python virtual environment tool for
development you can combine it with the "extra software" modules. The
complication comes because they already make use of such an environment.

First load the environment you want to use to compile your software. The LFRic
environment is used as an example.

.. code-block:: console

    $ module use $EXTRA_SOFTWARE
    $ module use $LFRIC_SOFTWARE
    $ module load environment/lfric/ifort

Then create a new virtual environment, unload the existing one and activate
the new.

.. code-block:: console

    $ python3 -m venv $VENV_DIR/fab_dev
    $ module unload python/3.7.0
    $ source $VENV_DIR/fab_dev/bin/activate

Install all the bits needed to install PSyclone and other parts of the build
process.

.. code-block:: console

    $ pip install --upgrade pip
    $ pip install Jinja2
    $ pip install six
    $ pip install fparser
    $ pip install pyparsing
    $ pip install sympy
    $ pip install jsonschema==3.0.2
    $ pip install configparser

Finally, install Fab in your working copy. This is done in "editable" mode
so that changes you make are immediately available through the environment.

.. code-block:: console

    $ pip install --editable $FAB_WORKING_COPY


Mixing Conda and Environemnt Modules
------------------------------------

In order to have both an environment capable of building C files and modern
Fortran compilers and the LFRic library stack you will need an awkward
amalgemation of conda environment and environment modules.

The conda environment is created as follows:

.. code-block:: console

    $ conda env create -f envs/conda/dev_env.yml
    $ conda activate sci-fab

Then :ref:`install fab<Install>`. This is done before any module commands.

The environment is set up *in a new terminal* as follows:

For use with gfortran:

.. code-block:: console

    $ module use $LFRIC_MODULES
    $ module load environment/lfric/gcc
    $ conda activate sci-fab
    $ PYTHONPATH=~/.conda/envs/sci-fab/lib/python3.7/site-packages:$PYTHONPATH

For use with ifort:

.. code-block:: console

    $ module use $LFRIC_MODULES
    $ module load environment/lfric/ifort
    $ conda activate sci-fab
    $ PYTHONPATH=~/.conda/envs/sci-fab/lib/python3.7/site-packages:$PYTHONPATH


PyCharm
-------

Running ``pycharm-community`` from the command line, after activating an
environment using any of the above approaches, PyCharm will be able to run Fab,
the tests, etc.
You can `set the project interpreter <https://www.jetbrains.com/help/pycharm/configuring-python-interpreter.html>`_
to be that in the conda environment.


Rose
----
Various configs for building projects using Rose on SPICE can be found in
`run_configs <https://github.com/metomi/fab/tree/master/run_configs>`_.


.. _MetOfficeDevelopment:

Developing Fab at the Met Office
================================

A few special notes for Met Office developers.

Acceptance tests
~~~~~~~~~~~~~~~~

For extra confidence, we have acceptance tests in the ``run_configs`` folder
which are not run as part of our automated github testing. You can run them on
the VDI using ``build_all.py``. However, this will choke your machine for some
time. There's a (misnamed) cron you can run nightly, ``run_configs/_cron/cron_system_tests.sh``.

There's also a rose suite which runs them on spice in ``run_configs/_rose_all``.

Build singularity image
~~~~~~~~~~~~~~~~~~~~~~~

The config file in envs/picasso defines the contents of a Singularity image
which is built by the experimental Picasso app. We can build this image using a
GitHub action, defined in ``.github/workflows/picasso_build.yml``.

This action is manually triggered. You have to push a branch to the metomi repo,
not a fork, then you can trigger the action from your branch. Please remember
to clean up the branch when you're finished.

You can see the image in artefactory
`here <https://metoffice.jfrog.io/ui/repos/tree/General/docker-local/picasso/metomi/fab/MyImage>`_.


See also
* :ref:`Run Singularity<Run Singularity>`
* `Picasso <https://metoffice.sharepoint.com/sites/scienceitteam/SitePages/Picasso.aspx>`_


