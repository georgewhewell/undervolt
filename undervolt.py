#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tool for undervolting Intel CPUs under Linux
"""

import argparse
import logging
import os
from glob import glob
from struct import pack

PLANES = {
    'core': 0,
    'gpu': 1,
    'cache': 2,
    'uncore': 3,
    'analogio': 4,
    'digitalio': 5,
}


def write_msr(val):
    """
    Use /dev/cpu/*/msr interface provided by msr module to read/write
    values from register 0x150.
    """
    n = glob('/dev/cpu/[0-9]*/msr')
    for c in n:
        logging.info("Writing {val} to {msr}".format(
            val=hex(val), msr=c))
        f = os.open(c, os.O_WRONLY)
        os.lseek(f, 0x150, os.SEEK_SET)
        os.write(f, pack('Q', val))
        os.close(f)
    if not n:
        raise OSError("msr module not loaded (run modprobe msr)")


def convert_offset(mV):
    """
    Calculate offset part of MSR value
    :param mV: voltage offset
    :return hex string

    >>> from undervolt import convert_offset
    >>> convert_offset(-50)
    'f9a00000'

    """
    return format(0xFFE00000 & ((round(mV*1.024) & 0xFFF) << 21), '08x')


def get_msr_value(plane, mV, write=True):
    """
    Get MSR value that writes (or read) offset to given plane
    :param plane: voltage plane as string (e.g. 'core', 'gpu')
    :param mV: offset as int (e.g. -50)
    :param write: generate value for writing (else reading)
    :return value as int ready to write to register

    # Write
    >>> from undervolt import get_msr_value
    >>> get_msr_value('core', -150)
    9223372113841225728
    >>> get_msr_value('gpu', -125)
    9223373213407379456
    >>> get_msr_value('cache', -150)
    9223374312864481280

    # Read
    >>> get_msr_value('core', None, False)
    9223372105574252544
    >>> get_msr_value('gpu', None, False)
    9223373205085880320
    >>> get_msr_value('cache', None, False)
    9223374304597508096

    """
    return int("0x80000{plane}1{write}{offset}".format(
        plane=PLANES[plane],
        write=int(write),
        offset=convert_offset(mV) if write else '0'*8,
    ), 0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbose', action='store_true',
                        help="print debug info")
    parser.add_argument('-f', '--force', action='store_true',
                        help="allow setting positive offsets")
    for plane in PLANES:
        parser.add_argument('--{}'.format(plane), type=int, help="offset (mV)")

    # parse args
    args = parser.parse_args()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # for each arg, try to set voltage
    for plane in PLANES:
        offset = getattr(args, plane)
        if offset is None:
            continue
        if offset > 0 and not args.force:
            raise ValueError("Use --force to set positive offset")
        logging.info('Setting {plane} offset to {offset}mV'.format(
            plane=plane, offset=offset))
        msr_value = get_msr_value(plane, offset)
        write_msr(msr_value)


if __name__ == '__main__':
    main()
