#!/usr/bin/python
# -*- coding: utf-8 -*-

from setuptools import setup

setup(name='import_video',
      version='0.1',
      description="what is the description",
      author='camio.com',
      author_email='support.camio.com',
      url='https://github.com/tnc-ca-geo/video-importer',
      install_requires=['hachoir_core','hachoir_parser','hachoir_metadata'],
      py_modules=["import_video"],
      license= 'BSD',
      package_data = {'': ['README.md']},
      entry_points = {
        'console_scripts': [
            'import_video = import_video:main'
            ],              
        },
      keywords='video',
     )
