#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tool for undervolting Intel CPUs under Linux
"""

import argparse
import logging
import os
import sys
import multiprocessing
from glob import glob
from struct import pack, unpack
import subprocess
try:  # Python3
    import configparser
except ImportError:  # Python2
    import ConfigParser as configparser

AC_STATE_NODE = os.environ.get(
    'AC_STATE_NODE', '/sys/class/power_supply/AC/online')
PLANES = {
    'core': 0,
    'gpu': 1,
    'cache': 2,
    'uncore': 3,
    'analogio': 4,
    # 'digitalio': 5, # not working?
}


def write_msr(val, msr=0x150):
    """
    Use /dev/cpu/*/msr interface provided by msr module to read/write
    values from register 0x150.
    Writes to all msr node on all CPUs available.
    """
    for i in range(multiprocessing.cpu_count()):
        c = '/dev/cpu/%d/msr' % i
        if not os.path.exists(c):
            raise OSError("msr module not loaded (run modprobe msr)")
        logging.info("Writing {val} to {msr}".format(val=hex(val), msr=c))
        f = os.open(c, os.O_WRONLY)
        os.lseek(f, msr, os.SEEK_SET)
        os.write(f, pack('Q', val))
        os.close(f)


def read_msr(msr=0x150, cpu=0):
    """
    Read a value from single msr node on given CPU (defaults to first)
    """
    n = '/dev/cpu/%d/msr' % (cpu,)
    f = os.open(n, os.O_RDONLY)
    os.lseek(f, msr, os.SEEK_SET)
    val, = unpack('Q', os.read(f, 8))
    logging.info("Read {val} from {n}".format(val=hex(val), n=n))
    os.close(f)
    return val


def convert_offset(mV):
    """
    Calculate offset part of MSR value
    :param mV: voltage offset
    :return hex string

    >>> from undervolt import convert_offset
    >>> format(convert_offset(-50), '08x')
    'f9a00000'

    """
    return convert_rounded_offset(int(round(mV*1.024)))


def unconvert_offset(y):
    """ For a given offset, return a value in mV that could have resulted in
        that offset.

        Inverts y to give the input value x closest to zero for values x in
        [-999, 1000]

    # Test that inverted values give the same output when re-converted.
    # NOTE: domain is [-1000, 1000] - other function, but scaled down by 1.024.
    >>> from undervolt import convert_offset, unconvert_offset
    >>> for x in range(-999, 1000):
    ...     y  = convert_offset(x)
    ...     x2 = unconvert_offset(y)
    ...     y2 = convert_offset(x2)
    ...     if y != y2 or x != x2:
    ...         result = (x, y, x2, y2)
    ...         assert result
    >>> unconvert_offset(0xf0000000)
    -125.0
    >>> unconvert_offset(0xf9a00000)
    -49.8046875
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


def pack_offset(plane_index, offset=None):
    """
    Get MSR value that writes (or read) offset to given plane
    :param plane: voltage plane index
    :param offset: voltage offset as hex string (omit for read)
    :return value as long int ready to write to register

    # Write
    >>> from undervolt import pack_offset
    >>> format(pack_offset(0, 0xecc00000), 'x')
    '80000011ecc00000'
    >>> format(pack_offset(1, 0xf0000000), 'x')
    '80000111f0000000'

    # Read
    >>> format(pack_offset(0), 'x')
    '8000001000000000'
    >>> format(pack_offset(1), 'x')
    '8000011000000000'

    """
    return ((1 << 63) | (plane_index << 40) | (1 << 36) |
        ((offset is not None) << 32) | (offset or 0))


def unpack_offset(msr_response):
    """
    Extract the offset component of the response and unpack to voltage.
    >>> from undervolt import unpack_offset
    >>> unpack_offset(0x0)
    0.0
    >>> unpack_offset(0x40000000000)
    0.0
    >>> unpack_offset(0x100f3400000)
    -99.609375
    """
    plane_index = int(msr_response / (1 << 40))
    return unconvert_offset(msr_response ^ (plane_index << 40))


def read_temperature():
    return read_msr(0x1a2) >> 24


def set_temperature(temp):
    write_msr((100 - temp) << 24, msr=0x1a2)


def read_offset(plane):
    """
    Write the 'read' value to mailbox, then re-read
    """
    plane_index = PLANES[plane]
    value_to_write = pack_offset(plane_index)
    write_msr(value_to_write)
    return unpack_offset(read_msr())


def set_offset(plane, mV):
    """"
    Set given voltage plane to offset mV
    Raises SystemExit if re-reading value returns something different
    """
    plane_index = PLANES[plane]
    logging.info('Setting {plane} offset to {mV}mV'.format(
        plane=plane, mV=mV))
    target = convert_offset(mV)
    write_value = pack_offset(plane_index, target)
    write_msr(write_value)
    # now check value set correctly
    want_mv = unconvert_offset(target)
    read_mv = read_offset(plane)
    if want_mv != read_mv:
        logging.error("Failed to apply {p}: set {t}, read {r}".format(
            p=plane, t=want_mv, r=read_mv))
        raise SystemExit(1)


def read_ac_state():
    """
    Returns True if AC is connected, else False
    """
    return open(AC_STATE_NODE).read() == '1\n'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbose', action='store_true',
                        help="print debug info")
    parser.add_argument('-f', '--force', action='store_true',
                        help="allow setting positive offsets")
    parser.add_argument('-r', '--read', action="store_true", help="read existing values")
    parser.add_argument('-t', '--temp', type=int, help="set temperature target")
    parser.add_argument('--temp-ac', type=int, help="set temperature target on AC power")
    parser.add_argument('--temp-bat', type=int, help="set temperature target on battery power")
    parser.add_argument('--throttlestop', type=str,
                        help="extract values from ThrottleStop")
    parser.add_argument('--tsindex', type=int,
                        default=0, help="ThrottleStop profile index")

    for plane in PLANES:
        parser.add_argument('--{}'.format(plane), type=int, help="offset (mV)")

    # print help if called with no args
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(1)

    args = parser.parse_args()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if not glob('/dev/cpu/*/msr'):
        subprocess.check_call(['modprobe', 'msr'])

    if (args.core or args.cache) and args.core != args.cache:
        logging.warn(
            "You have supplied different offsets for Core and Cache. "
            "The smaller of the two (or none if you only supplied one) will be applied to both planes."
        )

    # for each arg, try to set voltage
    for plane in PLANES:
        offset = getattr(args, plane)
        if offset is None:
            continue
        if offset > 0 and not args.force:
            raise ValueError("Use --force to set positive offset")
        set_offset(plane, offset)

    if args.temp and (args.temp_ac or args.temp_bat):
        logging.error("Set either --temp or --temp-ac/--temp-bat, not both")
        sys.exit(1)

    if args.temp:
        set_temperature(args.temp)

    if args.temp_ac and read_ac_state():
        set_temperature(args.temp_ac)

    if args.temp_bat and not read_ac_state():
        set_temperature(args.temp_bat)

    throttlestop = getattr(args, 'throttlestop')
    if throttlestop is not None:
        command = 'undervolt'
        tsindex = getattr(args, 'tsindex')
        config = configparser.ConfigParser()
        config.read(throttlestop)
        for plane in PLANES:
            hex_str = config.get('ThrottleStop', 'FIVRVoltage{plane}{profile}'.format(
                plane=PLANES[plane], profile=tsindex))
            hex_value = int(hex_str, 16)
            if hex_value != 0:
                offset = unconvert_offset(hex_value)
                command += ' --{plane} {offset}'.format(plane=plane, offset=offset)
        print(command)

    if args.read:
        print('temperature target: -{tjunc} ({temp}C)'.format(
            tjunc=read_temperature(),
            temp=100 - read_temperature(),
        ))
        for plane in PLANES:
            voltage = read_offset(plane)
            print('{plane}: {voltage} mV'.format(
                plane=plane, voltage=round(voltage, 2)))

if __name__ == '__main__':
    main()
