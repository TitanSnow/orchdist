from setuptools import setup
import orchdist
from orchdist import OrchDistribution


def read(filename):
    with open(filename, 'r', newline='\n') as f:
        return f.read()


setup(
    name='orchdist',
    packages=['orchdist'],
    distclass=OrchDistribution,
    test_suite='tests.suite',
    zip_safe=True,

    version=orchdist.__version__,
    author='TitanSnow',
    author_email='tttnns1024@gmail.com',
    url='https://github.com/TitanSnow/orchdist',
    description='A python module for executing ``distutils`` commands in concurrency',
    long_description=read('README.rst'),
    license='LGPL v2.1',
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GNU Lesser General Public License v2 (LGPLv2)',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Topic :: Utilities',
    ]
)
