from setuptools import setup
from orchdist import OrchDistribution


setup(
    name='orchdist',
    packages=['orchdist'],
    distclass=OrchDistribution,
)
