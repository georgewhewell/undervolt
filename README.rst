*Warning! This program is untested (apart from by myself) and it may damage your hardware! Use at your own risk.*

==================
undervolt |travis|
==================

.. |travis| image:: https://travis-ci.org/georgewhewell/undervolt.svg
    :target: https://travis-ci.org/georgewhewell/undervolt
    :alt: Build Status

*undervolt* is a program for undervolting Intel CPUs under Linux. It works in
a similar manner to the Windows program *ThrottleStop* (i.e, `MSR 0x150`). You
can apply a fixed voltage offset to one of 5 voltage planes, and override your
systems temperature target (CPU will throttle when this temperature is reached).

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

Read current offsets::

    $ undervolt --read
    temperature target: -0 (100C)
    core: 0.0 mV
    gpu: -19.53 mV
    cache: -30.27 mV
    uncore: -29.3 mV
    analogio: -70.31 mV

Apply -100mV offset to CPU Core and Cache::

    $ undervolt --core -100 --cache -100

Apply -75mV offset to GPU, -100mV to all other planes::

    $ undervolt --gpu -75 --core -100 --cache -100 --uncore -100 --analogio -100

Set temperature target to 97C::

    $ undervolt --temp 97

Generated the command to run to recreate your Throttlestop settings::

    $ undervolt --throttlestop ThrottleStop.ini --tsindex 3
    undervolt --core -100.5859375
    $ undervolt --throttlestop ThrottleStop.ini
    undervolt --core -125.0 --gpu -125.0 --cache -125.0

Usage
-----

.. code-block::

    $ undervolt -h
    usage: undervolt.py [-h] [-v] [-f] [-r] [-t TEMP]
                        [--temp-bat TEMP_BAT] [--throttlestop THROTTLESTOP]
                        [--tsindex TSINDEX] [--core CORE] [--gpu GPU]
                        [--cache CACHE] [--uncore UNCORE] [--analogio ANALOGIO]

    optional arguments:
      -h, --help            show this help message and exit
      -v, --verbose         print debug info
      -f, --force           allow setting positive offsets
      -r, --read            read existing values
      -t TEMP, --temp TEMP  set temperature target on AC (and battery power if --temp-bat is not used)
      --temp-bat TEMP_BAT   set temperature target on battery power
      --throttlestop THROTTLESTOP
                            extract values from ThrottleStop
      --tsindex TSINDEX     ThrottleStop profile index
      --core CORE           offset (mV)
      --gpu GPU             offset (mV)
      --cache CACHE         offset (mV)
      --uncore UNCORE       offset (mV)
      --analogio ANALOGIO   offset (mV)

Running automatically on boot (systemd)
---------------------------------------

First, create a unit file ``/etc/systemd/system/undervolt.service`` with
following contents, replacing the arguments with your own offsets::

  [Unit]
  Description=undervolt

  [Service]
  Type=oneshot
  # If you have installed undervolt globally (via sudo pip install):
  ExecStart=undervolt -v --core -150 --cache -150 --gpu -100
  # If you want to run from source:
  # ExecStart=/path/to/undervolt.py -v --core -150 --cache -150 --gpu -100

Check that your script works::

  $ systemctl start undervolt

Then create a timer ``/etc/systemd/system/undervolt.timer`` to trigger the task periodically: ::

  [Unit]
  Description=Apply undervolt settings

  [Timer]
  Unit=undervolt.service
  # Wait 2 minutes after boot before first applying
  OnBootSec=2min
  # Run every 30 seconds
  OnUnitActiveSec=30

  [Install]
  WantedBy=multi-user.target

Now enable and start the timer::

  $ systemctl enable undervolt.timer
  $ systemctl start undervolt.timer

By including the *OnBootSec* command, settings will not be immediately applied.
If you have set overly-aggressive offsets, you will have a short period to
disable the timer before it crashes your system::

  $ systemctl stop undervolt.timer

Now you can edit your ``undervolt.service`` before re-starting the timer.

Running automatically on boot (runit)
-------------------------------------

First, create a directory for the service::

  $ sudo mkdir -p /etc/sv/undervolt

Then create a file named "run" in that directory and edit it to contain these contents::

  #!/bin/sh
  undervolt --core -85 --uncore -85 --analogio -85 --cache -85 --gpu -85
  sleep 60

Replace the offsets with your own. Then mark the file as executable::

  $ sudo chmod a+x /etc/sv/undervolt/run

Then enable the service::

  $ sudo ln -s /etc/sv/undervolt /var/services/

Hardware support
----------------

Undervolting should work on any CPU later than Haswell.

======================== ========= ==========
      System                CPU     Working? 
======================== ========= ==========
Acer Aspire 7 (A715-71G) i5-7300HQ Yes
Acer Nitro 5             i5-7300HQ Yes
Dell Latitude 5480       i5-6300U  Yes
Dell Latitude 7390       i7-8650U  Yes
Dell Precision 5530      i9-8950HK Yes
Dell Precision M3800     i7-4712HQ Yes
Dell XPS 13 9343         i5-5200U  Yes
Dell XPS 15 9530         i7-4712HQ Yes
Dell XPS 15 9550         i7-6700HQ Yes
Dell XPS 15 9560         i7-7700HQ Yes
Dell XPS 15 9570         i9-8950HK Yes
Dell XPS 15 9575         i7-8705G  Yes
HP Spectre X360          i7-8809G  Yes
HP Zbook Studio G5       i7-8750H  Yes
Lenovo Thinkpad T470p    i7-7700HQ Yes
Lenovo Thinkpad x250     i7-5600U  Yes
Lenovo X1 Gen 5          i7-7500U  Yes
Lenovo X1 Yoga Gen 2     i7-7600U  Yes
Lenovo Yoga 920          i7-8550U  Yes
MacBook Air Mid 2013     i5-4250U  Yes
Lenovo Thinkpad T430     i7-3610QM No
Toshiba Chromebook 2     N2840     No
Asus FX504GE             i7-8750h  Yes
======================== ========= ==========

Troubleshooting
---------------

- **Core or Cache offsets have no effect.**
  It is not possible to set different offsets for CPU Core and Cache. The CPU
  will take the smaller of the two offsets, and apply that to both CPU and
  Cache. A warning message will be displayed if you attempt to set different
  offsets.

- ``OSError: [Errno 1] Operation not permitted``
  First try running with ``sudo``. If the error persists, your system is
  probably booted in Secure Boot mode. In this case, the Linux kernel will
  prevent userspace programs (even as root) from writing to the CPU's
  model-specific registers. Disable UEFI Secure Boot in your system's BIOS
  and the error should go away.


GUI
----------------
There is also a small gui written in Java avaiable here: https://github.com/zmalrobot/JavaLinuxUndervolt

It will allow you to set each value core, gpu, cache, uncore, analogio (temperature target isn't implemented yet),save a profile, load a profile and reset the value.


Credit
------
This project is a trivial wrapper around the work of others from the following resources:

- https://github.com/mihic/linux-intel-undervolt
- http://forum.notebookreview.com/threads/undervolting-e-g-skylake-in-linux.807953
- https://forums.anandtech.com/threads/what-controls-turbo-core-in-xeons.2496647

Many thanks to all who contributed.
