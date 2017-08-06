========
orchdist
========

A python module for executing ``distutils`` commands in concurrency

Intro
=====

orchdist is a drop-in enhancement of ``distutils`` -- the python standard library for building and installing python modules. It provides the features of concurrent building etc

Basic Usage
===========

To basicly enable orchdist in ``setup.py``, just replace the ``distclass``

.. code-block:: diff

    from setuptools import setup
  + from orchdist import OrchDistribution


    setup(
        ...
  +     distclass=OrchDistribution
    )
