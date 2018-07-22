#!/usr/bin/env python3

__author__ = 'Gennady Kovalev <gik@bigur.ru>'
__copyright__ = '(c) 2016-2018 Business group for development management'
__licence__ = 'For license information see LICENSE'

from setuptools import setup


setup(
    name='bigur-fsm',
    version='3.0.1',

    description='Поддержка конечного автомата для python',
    url='https://github.com/bigur/fsm',

    author='Геннадий Ковалёв',
    author_email='gik@bigur.ru',

    license='BSD-3-Clause',

    classifiers=[
        'Development Status :: 3 - Alpha',
        'Programming Language :: Python :: 3.5',
    ],

    keywords=['bigur', 'fsm', 'finite state machine'],

    packages=['bigur/fsm']
)
