#!/usr/bin/env python
# -*- coding: utf-8 -*-
from os.path import dirname, join
from setuptools import setup
import doctest


def test_suite():
    return doctest.DocTestSuite('undervolt')


setup(
    name='undervolt',
    version='0.2.7',
    description='Undervolt Intel CPUs under Linux',
    long_description=open(
        join(dirname(__file__), 'README.rst')).read(),
    url='http://github.com/georgewhewell/undervolt',
    author='George Whewell',
    author_email='georgerw@gmail.com',
    license='GPL',
    py_modules=['undervolt'],
    test_suite='setup.test_suite',
    entry_points={
        'console_scripts': [
            'undervolt=undervolt:main',
        ],
    },
    keywords=['undervolt', 'intel', 'linux'],
    classifiers=[
        'Development Status :: 3 - Alpha',
        'License :: OSI Approved :: GNU General Public License (GPL)',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 3',
    ],
)
