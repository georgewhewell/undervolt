#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tool for undervolting Intel CPUs under Linux
"""

import argparse
import logging
import os
from glob import glob
from struct import pack, unpack

PLANES = {
    'core': 0,
    'gpu': 1,
    'cache': 2,
    'uncore': 3,
    'analogio': 4,
#   'digitalio': 5, # not working?
}


def write_msr(val, msr=0x150):
    """
    Use /dev/cpu/*/msr interface provided by msr module to read/write
    values from register 0x150.
    """
    n = glob('/dev/cpu/[0-9]*/msr')
    for c in n:
        logging.info("Writing {val} to {msr}".format(
            val=hex(val), msr=c))
        f = os.open(c, os.O_WRONLY)
        os.lseek(f, msr, os.SEEK_SET)
        os.write(f, pack('Q', val))
        os.close(f)
    if not n:
        raise OSError("msr module not loaded (run modprobe msr)")


def read_msr(msr=0x150, cpu=0):
    n = '/dev/cpu/%d/msr' % (cpu,)
    f = os.open(n, os.O_RDONLY)
    os.lseek(f, msr, os.SEEK_SET)
    val = unpack('Q', os.read(f, 8))[0]
    logging.info("Read {val} from {n}".format(val=hex(val), n=n))
    os.close(f)
    return val


def read_offset(plane):
    value_to_write = pack_offset(plane)
    write_msr(value_to_write)
    return read_msr()


def convert_offset(mV):
    """
    Calculate offset part of MSR value
    :param mV: voltage offset
    :return hex string

    >>> from undervolt import convert_offset
    >>> convert_offset(-50)
    'f9a00000'

    """
    return format(convert_rounded_offset(int(round(mV*1.024))), '08x')

def unconvert_offset(y):
    """ For a given offset, return a value in mV that could have resulted in
        that offset.

        Inverts y to give the input value x closest to zero for values x in
        [-1000, 1000]

    # Test that inverted values give the same output when re-converted.
    # NOTE: domain is [-1000, 1000] - other function, but scaled down by 1.024.
    >>> from undervolt import convert_offset, unconvert_offset
    >>> domain = [ 1000 - x for x in range(0, 2000) ]
    >>> result = True
    >>> for x in domain:
    ...     y  = int(convert_offset(x), 16)
    ...     x2 = round(unconvert_offset(y))
    ...     y2 = int(convert_offset(x2), 16)
    ...     if y != y2 or x != x2:
    ...         result = (x, y, x2, y2)
    ...         break
    >>> result
    True
    """
    return unconvert_rounded_offset(y) / 1.024


def convert_rounded_offset(x):
    return 0xFFE00000 & ((x & 0xFFF) << 21)


def unconvert_rounded_offset(y):
    """
    >>> from undervolt import convert_offset, unconvert_offset
    >>> domain = [ 1024 - x for x in range(0, 2048) ]
    >>> all( x == unconvert_rounded_offset(convert_rounded_offset(x)) for x in domain )
    True
    """
    x = y >> 21
    return x if x <= 1024 else - (2048 - x)


def pack_offset(plane, offset='0'*8):
    """
    Get MSR value that writes (or read) offset to given plane
    :param plane: voltage plane as string (e.g. 'core', 'gpu')
    :param mV: offset as int (e.g. -50)
    :param write: generate value for writing (else reading)
    :return value as int ready to write to register

    # Write
    >>> from undervolt import pack_offset
    >>> pack_offset('core', 'ecc00000')
    9223372113841225728
    >>> pack_offset('gpu', 'f0000000')
    9223373213407379456
    >>> pack_offset('cache', 'ecc00000')
    9223374312864481280

    # Read
    >>> pack_offset('core')
    9223372105574252544
    >>> pack_offset('gpu')
    9223373205085880320
    >>> pack_offset('cache')
    9223374304597508096

    """
    return int("0x80000{plane}1{write}{offset}".format(
        plane=PLANES[plane],
        write=int(offset is not '0'*8),
        offset=offset,
    ), 0)


def set_offset(plane, mV):
    logging.info('Setting {plane} offset to {mV}mV'.format(
        plane=plane, mV=mV))
    target = convert_offset(mV)
    write_value = pack_offset(plane, target)
    write_msr(write_value)
    # now check value set correctly
    read = format(read_offset(plane), '08x')
    if read != target:
        logging.error("Failed to set {p}: expected {t}, read {r}".format(
            p=plane, t=target, r=format(read, '08x')))
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbose', action='store_true',
                        help="print debug info")
    parser.add_argument('-f', '--force', action='store_true',
                        help="allow setting positive offsets")
    parser.add_argument('-r', '--read', action="store_true", help="read existing values")

    for plane in PLANES:
        parser.add_argument('--{}'.format(plane), type=int, help="offset (mV)")

    # parse args
    args = parser.parse_args()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.read:
        for plane in PLANES:
            msr_value = read_offset(plane)
            voltage = unconvert_offset(msr_value)
            print('{plane}: {voltage} mV'.format(
                plane=plane, voltage=round(voltage, 2)))

    # for each arg, try to set voltage
    for plane in PLANES:
        offset = getattr(args, plane)
        if offset is None:
            continue
        if offset > 0 and not args.force:
            raise ValueError("Use --force to set positive offset")
        set_offset(plane, offset)


if __name__ == '__main__':
    main()
