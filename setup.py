from setuptools import setup
from orchdist import OrchDistribution


setup(
    name='orchdist',
    packages=['orchdist'],
    distclass=OrchDistribution,
    test_suite='tests.suite',
    zip_safe=True,
    install_requires=['asyncio>=3.4.1;python_version=="3.3"'],
    setup_requires=['setuptools>=24.2.0'],
    python_requires='~=3.0',
)
