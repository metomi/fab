.. _Install:


Installing Fab
**************
Once you've :ref:`setup an environment<Environment>`,
you can install the latest release of `Fab from PyPI <https://pypi.org/project/sci-fab/>`_:

.. code-block:: console

    $ pip install sci-fab

The minimum Python dependencies (e.g. `fparser <https://github.com/stfc/fparser>`_)
will also be installed automatically.

.. note::

    When installing from PyPI, please be sure to install **sci-fab**, not *fab*.
    There is already a package on PyPI called *fab*, which installs something else entirely.


Extra features
==============
You can install some extra Python packages to enable more features.
This will install.

* `matplotlib <https://matplotlib.org/>`_ for producing metrics graphs after a run
* `psyclone <https://github.com/stfc/PSyclone>`_ for building LFRic, and more

.. code-block:: console

    $ pip install sci-fab[features]


Configuration
=============

.. _Configure Fab Workspace:

Fab workspace
-------------

You can optionally tell Fab where it's workspace should live.
This can be useful on systems where your home space is on a slower drive,
or when you like your build to be next to your source::

    $ export FAB_WORKSPACE=<fast_drive>/fab_workspace

By default, Fab will create a project workspaces inside ``~/fab-workspace``.


Development
===========

People looking to develop Fab will likely want to
:ref:`Install from source<Install from source>`

Met Office Users
================

There are instructions specific to people wanting to
:ref:`use Fab at the Met Office<MetOfficeUsage>`.
