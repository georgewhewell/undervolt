#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tool for undervolting Intel CPUs under Linux
"""

import argparse
import logging
import os
import re
import sys
import multiprocessing
from collections import namedtuple
from glob import glob
from struct import pack, unpack
import subprocess
try:  # Python3
    import configparser
except ImportError:  # Python2
    import ConfigParser as configparser

try: # Python >=3.3
    from math import log2
except ImportError:
    from math import log
    def log2(x):
        return log(x, 2)
__version__ = '0.3.0'

AC_STATE_NODE = os.environ.get(
    'AC_STATE_NODE', (glob('/sys/class/power_supply/AC*/online') + [None])[0])
PLANES = {
    'core': 0,
    'gpu': 1,
    'cache': 2,
    'uncore': 3,
    'analogio': 4,
    # 'digitalio': 5, # not working?
}

MSR = namedtuple('MSR', ['addr_voltage_offsets', 'addr_units', 'addr_power_limits', 'addr_temp'])
ADDRESSES = MSR(0x150, 0x606, 0x610, 0x1a2) # Default (Core iX 6th, 7th, 8th, 9th gen etc.)

# 0.2.9 removed --temp-ac flag without warning
# accept it for now and show deprecation
# remove in 0.3
if any('temp-ac' in arg for arg in sys.argv):
    logging.warning("Got deprecated flag --temp-ac, assuming --temp")
    sys.argv = [arg.replace('temp-ac', 'temp') for arg in sys.argv]


def valid_cpus():
    """
    Get max processor index from multiprocess.count(), then check which
    values are valid under /dev/cpu/
    """

    cpus = []
    max_cpus = multiprocessing.cpu_count()
    for i in range(max_cpus):
        if os.path.isdir("/dev/cpu/%d" % i):
            cpus.append(i)

    return cpus

def write_msr(val, addr):
    """
    Use /dev/cpu/*/msr interface provided by msr module to read/write
    values from register addr.
    Writes to all msr node on all CPUs available.
    """
    for i in valid_cpus():
        c = '/dev/cpu/%d/msr' % i
        if not os.path.exists(c):
            raise OSError("msr module not loaded (run modprobe msr)")
        logging.info("Writing {val} to {msr}".format(val=hex(val), msr=c))
        f = os.open(c, os.O_WRONLY)
        os.lseek(f, addr, os.SEEK_SET)
        os.write(f, pack('Q', val))
        os.close(f)


def read_msr(addr, cpu=0):
    """
    Read a value from single msr node on given CPU (defaults to first)
    """
    n = '/dev/cpu/%d/msr' % (cpu,)
    f = os.open(n, os.O_RDONLY)
    os.lseek(f, addr, os.SEEK_SET)
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


def read_temperature(msr):
    return (read_msr(msr.addr_temp) & (127 << 24)) >> 24


def set_temperature(temp, msr):
    write_msr((100 - temp) << 24, addr=msr.addr_temp)


def read_offset(plane, msr):
    """
    Write the 'read' value to mailbox, then re-read
    """
    plane_index = PLANES[plane]
    value_to_write = pack_offset(plane_index)
    write_msr(value_to_write, msr.addr_voltage_offsets)
    return unpack_offset(read_msr(msr.addr_voltage_offsets))


def set_offset(plane, mV, msr):
    """
    Set given voltage plane to offset mV
    Raises SystemExit if re-reading value returns something different
    """
    plane_index = PLANES[plane]
    logging.info('Setting {plane} offset to {mV}mV'.format(
        plane=plane, mV=mV))
    target = convert_offset(mV)
    write_value = pack_offset(plane_index, target)
    write_msr(write_value, msr.addr_voltage_offsets)
    # now check value set correctly
    want_mv = unconvert_offset(target)
    read_mv = read_offset(plane, msr)
    if want_mv != read_mv:
        logging.error("Failed to apply {p}: set {t}, read {r}".format(
            p=plane, t=want_mv, r=read_mv))
        raise SystemExit(1)


class PowerLimit:
    short_term_enabled=None
    short_term_power=None
    short_term_time=None
    long_term_enabled=None
    long_term_power=None
    long_term_time=None
    locked=False
    backup_rest=None  # Backup of the bits that are not written


# Author: Stefan Fabian
# Use at your own risk!
def read_power_limit(msr):
    def to_seconds(val, unit):
        return 2**(val & 0x1f) * (1 + ((val >> 5) & 0x3) / 4.0) / unit
    units = read_msr(msr.addr_units)
    val = read_msr(msr.addr_power_limits)
    power_unit = round(2**(units & 0xf))
    time_unit = round(2**((units >> 16) & 0xf))
    result = PowerLimit()
    result.short_term_enabled = bool((val >> 47) & 0x1)
    result.short_term_power = ((val >> 32) & 0x7fff) / power_unit
    result.short_term_time = to_seconds(val >> 49, time_unit)
    result.long_term_enabled = bool((val >> 15) & 0x1)
    result.long_term_power = (val & 0x7fff) / power_unit
    result.long_term_time = to_seconds(val >> 17, time_unit)
    result.locked = bool((val >> 63) & 1)
    result.backup_rest = val & 0x7f010000ff010000
    return result

# Author: Stefan Fabian
# Use at your own risk!
def set_power_limit(power_limit, msr):
    def from_seconds(val, unit):
        # The formula 2^x*(1+y/4) has two variables and can not be solved analytically
        # y is 2 bytes, hence we only need to check 4 values
        val = val * unit
        if log2(val / 1.75) >= 0x1f:
            return 0xfe
        min_err = 1E9
        result = 0
        for y in range(4):
            multiplier = (1 + y / 4.0)
            val_mult = val / multiplier
            exp = log2(val_mult)
            exp_int = int(exp)
            # Due to the logarithm, we can't just round but have to check which one is closer to 2**exp
            if val_mult - 2**exp_int >= 2**(exp_int + 1) - val_mult:
                exp_int += 1
            if exp_int > 0x1f:
                exp_int = 0x1f
            back_val = 2**exp_int * multiplier
            if abs(back_val - val) < min_err:
                min_err = abs(back_val - val)
                result = int(y) << 5 | int(exp_int)
        return result
    old_limit = read_power_limit(msr)
    if old_limit.locked:
        logging.error("Can not write power limit because it is locked!")
        raise SystemExit(1)
    units = read_msr(msr.addr_units)
    power_unit = round(2**(units & 0xf))
    time_unit = round(2**((units >> 16) & 0xf))

    write_value = old_limit.backup_rest
    # short term enabled
    if power_limit.short_term_enabled is None:
        power_limit.short_term_enabled = old_limit.short_term_enabled
    write_value |= (1 if power_limit.short_term_enabled else 0) << 47
    # short term power
    if power_limit.short_term_power is None:
        power_limit.short_term_power = old_limit.short_term_power
    short_term_power = int(power_limit.short_term_power * power_unit)
    if short_term_power < 0 or short_term_power > 0x7fff:
        logging.error("Short term power out of range ({} > 0x7fff)!".format(short_term_power))
        raise SystemExit(1)
    write_value |= short_term_power << 32
    # short term time
    if power_limit.short_term_time is None:
        power_limit.short_term_time = old_limit.short_term_time
    short_term_time = from_seconds(power_limit.short_term_time, time_unit)
    write_value |= short_term_time << 49
    # long term enabled
    if power_limit.long_term_enabled is None:
        power_limit.long_term_enabled = old_limit.long_term_enabled
    write_value |= (1 if power_limit.long_term_enabled else 0) << 15
    # long term power
    if power_limit.long_term_power is None:
        power_limit.long_term_power = old_limit.long_term_power
    long_term_power = int(power_limit.long_term_power * power_unit)
    if long_term_power < 0 or long_term_power > 0x7fff:
        logging.error("Long term power out of range ({} > 0x7fff)!".format(long_term_power))
        raise SystemExit(1)
    write_value |= long_term_power
    # long term time
    if power_limit.long_term_time is None:
        power_limit.long_term_time = old_limit.long_term_time
    long_term_time = from_seconds(power_limit.long_term_time, time_unit)
    write_value |= long_term_time << 17
    # locked
    if power_limit.locked is None:
        power_limit.locked = old_limit.locked
    write_value |= (1 if power_limit.locked else 0) << 63

    # Write the new power limit
    write_msr(write_value, msr.addr_power_limits)
    val = read_msr(msr.addr_power_limits)
    if val != write_value:
        logging.error("Failed to apply power limit: Tried to set {}, read {}".format(write_value, val))
        raise SystemExit(1)



def read_ac_state():
    """
    Returns True if AC is connected, else False
    """
    if AC_STATE_NODE:
        return open(AC_STATE_NODE).read() == '1\n'
    # Assume no battery if the /sys entry is missing.
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', action='version', version='%(prog)s {version}'.format(version=__version__))
    parser.add_argument('-v', '--verbose', action='store_true',
                        help="print debug info")
    parser.add_argument('-f', '--force', action='store_true',
                        help="allow setting positive offsets")
    parser.add_argument('-r', '--read', action="store_true", help="read existing values")
    parser.add_argument('-t', '--temp', type=int, help="set temperature target on AC (and battery power if --temp-bat is not used)")
    parser.add_argument('--temp-bat', type=int, help="set temperature target on battery power")
    parser.add_argument('--throttlestop', type=str,
                        help="extract values from ThrottleStop")
    parser.add_argument('--tsindex', type=int,
                        default=0, help="ThrottleStop profile index")
    parser.add_argument('-p1', '--power-limit-long', nargs=2, help="P1 Power Limit (W) and Time Window (s)", metavar=('POWER_LIMIT', 'TIME_WINDOW'))
    parser.add_argument('-p2', '--power-limit-short', nargs=2, help="P2 Power Limit (W) and Time Window (s)", metavar=('POWER_LIMIT', 'TIME_WINDOW'))
    parser.add_argument('--lock-power-limit', action='store_true',
                        help="Locks the set power limit. Once they are locked, they can not be modified until next RESET (e.g., Reboot).")

    for plane in PLANES:
        parser.add_argument('--{}'.format(plane), type=int, help="offset (mV)")

    # print help if called with no args
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(1)

    args = parser.parse_args()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    msr = ADDRESSES

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
        set_offset(plane, offset, msr)

    if (args.temp and read_ac_state()) or (args.temp and not args.temp_bat):
        set_temperature(args.temp, msr)

    if args.temp_bat and not read_ac_state():
        set_temperature(args.temp_bat, msr)

    power_limit = PowerLimit()
    if args.power_limit_long:
        power_limit.long_term_enabled = True
        power_limit.long_term_power = float(args.power_limit_long[0])
        power_limit.long_term_time = float(args.power_limit_long[1])
    if args.power_limit_short:
        power_limit.short_term_enabled = True
        power_limit.short_term_power = float(args.power_limit_short[0])
        power_limit.short_term_time = float(args.power_limit_short[1])
    if args.lock_power_limit:
        power_limit.locked = True
    if power_limit.short_term_enabled is not None or power_limit.long_term_enabled is not None:
        set_power_limit(power_limit, msr)    

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
        temp = read_temperature(msr)
        print('temperature target: -{tjunc} ({temp}C)'.format(
            tjunc=temp,
            temp=100 - temp
        ))
        for plane in PLANES:
            voltage = read_offset(plane, msr)
            print('{plane}: {voltage} mV'.format(
                plane=plane, voltage=round(voltage, 2)))
        power_limit = read_power_limit(msr)
        print('powerlimit: {}W (short: {}s - {}) / {}W (long: {}s - {}){}'.format(
            power_limit.short_term_power,
            power_limit.short_term_time,
            'enabled' if power_limit.short_term_enabled else 'disabled',
            power_limit.long_term_power,
            power_limit.long_term_time,
            'enabled' if power_limit.long_term_enabled else 'disabled',
            ' [locked]' if power_limit.locked else ''
        ))

if __name__ == '__main__':
    main()
