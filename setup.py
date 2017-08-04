from setuptools import setup
from orchdist import OrchDistribution


setup(
    name='orchdist',
    packages=['orchdist'],
    distclass=OrchDistribution,
    test_suite='tests.suite',
    zip_safe=True,
)
