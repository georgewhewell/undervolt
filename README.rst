*Warning!*

*This program is untested (apart from by myself) and it may damage your hardware! Use at your own risk.*

=========
undervolt
=========

*undervolt* is a program for undervolting Intel CPUs under Linux. It works in
a similar manner to the Windows program *ThrottleStop* (i.e, `MSR 0x150`). You
can apply a fixed voltage offset to one of 5 voltage planes.

For more information, read
`here <https://github.com/mihic/linux-intel-undervolt>`_.

Installing
----------

From PyPi::

    $ pip install undervolt

From source::

    $ git clone https://github.com/georgewhewell/undervolt.git

Examples
--------

Apply -100mV offset to CPU Core and Cache::

    undervolt --core -100 --cache -100

Apply -75mV offset to GPU, -100mV to all other planes::

    undervolt --gpu -75 --core -100 --cache -100 --uncore -100 --analogio -100

Usage
-----

.. code-block:: bash

    $ undervolt -h
    usage: undervolt [-h] [-v] [-f] [--core CORE] [--gpu GPU] [--cache CACHE]
                     [--uncore UNCORE] [--analogio ANALOGIO]
                     [--digitalio DIGITALIO]
    optional arguments:
      -h, --help            show this help message and exit
      -v, --verbose         print debug info
      -f, --force           allow setting positive offsets
      --core CORE           offset (mV)
      --gpu GPU             offset (mV)
      --cache CACHE         offset (mV)
      --uncore UNCORE       offset (mV)
      --analogio ANALOGIO   offset (mV)
      --digitalio DIGITALIO offset (mV)

Credit
------
This project is trivial wrapper around the work of others from the following resources:

- https://github.com/mihic/linux-intel-undervolt
- http://forum.notebookreview.com/threads/undervolting-e-g-skylake-in-linux.807953
- https://forums.anandtech.com/threads/what-controls-turbo-core-in-xeons.2496647

Many thanks to all who contributed.
