#!/usr/bin/env python

from distutils.core import setup

setup(name='asahi_firmware',
      version='0.1',
      description='Asahi Linux firmware tools',
      author='Hector Martin',
      author_email='marcan@marcan.st',
      url='https://github.com/AsahiLinux/asahi-installer/',
      packages=['asahi_firmware'],
      entry_points={"console_scripts": ["asahi-fwextract = asahi_firmware.update:main"]}
     )
