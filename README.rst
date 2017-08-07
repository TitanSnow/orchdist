========
orchdist
========

A python module for executing ``distutils`` commands in concurrency

.. image:: https://img.shields.io/travis/TitanSnow/orchdist.svg?style=flat-square
  :target: https://travis-ci.org/TitanSnow/orchdist
  :alt: build
.. image:: https://img.shields.io/codecov/c/github/TitanSnow/orchdist.svg?style=flat-square
  :target: https://codecov.io/gh/TitanSnow/orchdist
  :alt: coverage
.. image:: https://img.shields.io/pypi/v/orchdist.svg?style=flat-square
  :target: https://pypi.org/project/orchdist
  :alt: version
.. image:: https://img.shields.io/pypi/l/orchdist.svg?style=flat-square
  :target: https://pypi.org/project/orchdist
  :alt: license

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
