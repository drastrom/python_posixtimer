#!/usr/bin/env python

# POSIX Alarm Timer example using Python ctypes
#
# Author: David Coles <coles.david@gmail.com>
# Date: 2012-03-19
#
# To the extent possible under law, the author(s) have dedicated all copyright
# and related and neighboring rights to this software to the public domain
# worldwide. This software is distributed without any warranty.

# POSIX Alarm Timers in Linux (see https://lwn.net/Articles/429925/) are one
# way to get a system to wake from suspend. The basic idea is to use the
# normal POSIX Timer interface to get the kernel to set an alarm on the RTC so
# an application doesn't have to deal with RTC clock drift or fight other
# applications for use of the RTC alarm.
#
# Requires Linux 3.0 (or greater) and must be run by with CAP_WAKE_ALARM or as
# root to allow the creation of a CLOCK_REALTIME_ALARM clock.

import ctypes
import errno
import sys

__all__ = [
        # Clock IDs
        'CLOCK_REALTIME', 'CLOCK_MONOTONIC', 'CLOCK_PROCESS_CPUTIME_ID',
        'CLOCK_THREAD_CPUTIME_ID', 'CLOCK_MONOTONIC_RAW',
        'CLOCK_REALTIME_COARSE', 'CLOCK_MONOTONIC_COARSE', 'CLOCK_BOOTTIME',
        'CLOCK_REALTIME_ALARM', 'CLOCK_BOOTTIME_ALARM', 'CLOCK_TAI',
        # Flags for timer_settime
        'TIMER_ABSTIME',
        # Classes
        'PosixTimer'
]

if not sys.platform.startswith("linux"):
    raise NotImplementedError("Only implemented for Linux")

# C libraries
_librt = ctypes.CDLL("librt.so", use_errno=True)

# Most of the stuff here is all the structs and types required to make this
# work with ctypes. Basically this is all taken straight out of bits/siginfo.h
# on Linux and thus is highly non-portable and otherwise a really bad idea.
#
# ... but it does let you do it from Python. ;)

# Types
_clockid_t = ctypes.c_int32
_pid_t = ctypes.c_int32
_timer_t = ctypes.c_void_p
_time_t = ctypes.c_long

# Clock IDs
CLOCK_REALTIME = _clockid_t(0)
CLOCK_MONOTONIC = _clockid_t(1)
CLOCK_PROCESS_CPUTIME_ID = _clockid_t(2)
CLOCK_THREAD_CPUTIME_ID = _clockid_t(3)
CLOCK_MONOTONIC_RAW = _clockid_t(4)
CLOCK_REALTIME_COARSE = _clockid_t(5)
CLOCK_MONOTONIC_COARSE = _clockid_t(6)
CLOCK_BOOTTIME = _clockid_t(7)
CLOCK_REALTIME_ALARM = _clockid_t(8)
CLOCK_BOOTTIME_ALARM = _clockid_t(9)
CLOCK_TAI = _clockid_t(11)

# Flags for timer_settime
TIMER_ABSTIME = ctypes.c_int(1)

# Notification IDs
_SIGEV_SIGNAL = ctypes.c_int(0)
_SIGEV_NONE = ctypes.c_int(1)
_SIGEV_THREAD = ctypes.c_int(2)


# The sigval union from <signal.h>
class _Union_sigval(ctypes.Union):
    _fields_ = [
        ("sival_int", ctypes.c_int),
        ("sival_ptr", ctypes.c_void_p),
    ]


# The SIGEV_THREAD callback funtion type
_sigev_notify_function = ctypes.CFUNCTYPE(None, _Union_sigval)


# The sigevent structure from <signal.h>
class _Struct__sigev_thread(ctypes.Structure):
    _fields_ = [
        ("sigev_notify_function", _sigev_notify_function),
        ("sigev_notify_attributes", ctypes.c_void_p),
    ]


class _Struct__sigev_un(ctypes.Union):
    _anonymous_ = ("_sigev_thread", )
    _fields_ = [
        ("_pad", ctypes.c_int * (12 if sys.maxsize == 2**63-1 else 13)),
        ("_tid", _pid_t),
        ("_sigev_thread", _Struct__sigev_thread),
    ]


class _Struct_sigevent(ctypes.Structure):
    _anonymous_ = ("_sigev_un", )
    _fields_ = [
        ("sigev_value", _Union_sigval),
        ("sigev_signo", ctypes.c_int),
        ("sigev_notify", ctypes.c_int),
        ("_sigev_un", _Struct__sigev_un),
    ]

# The timespec struct from <time.h>
class _Struct_timespec(ctypes.Structure):
    _fields_ = [
        ("tv_sec", _time_t),
        ("tv_nsec", ctypes.c_long)
    ]

# The itimerspec struct from <time.h>
class _Struct_itimerspec(ctypes.Structure):
    _fields_ = [
        ("it_interval", _Struct_timespec),  # Interval for periodic timer
        ("it_value", _Struct_timespec),  # First expiration
    ]

def _error_handler(value):
    if value == -1:
        err = ctypes.get_errno()
        raise OSError(err, os.strerror(err))
    return value

_librt.timer_create.argtypes = [_clockid_t, ctypes.POINTER(_Struct_sigevent), ctypes.POINTER(_timer_t)]
_librt.timer_create.restype = _error_handler
_librt.clock_gettime.argtypes = [_clockid_t, ctypes.POINTER(_Struct_timespec)]
_librt.clock_gettime.restype = _error_handler
_librt.timer_delete.argtypes = [_timer_t]
_librt.timer_delete.restype = _error_handler
_librt.timer_getoverrun.argtypes = [_timer_t]
_librt.timer_getoverrun.restype = _error_handler
_librt.timer_settime.argtypes = [_timer_t, ctypes.c_int32, ctypes.POINTER(_Struct_itimerspec), ctypes.POINTER(_Struct_itimerspec)]
_librt.timer_settime.restype = _error_handler
_librt.timer_gettime.argtypes = [_timer_t, ctypes.POINTER(_Struct_itimerspec)]
_librt.timer_gettime.restype = _error_handler

def _second_nsec_to_float(sec_nsec):
    return sec_nsec[0] + sec_nsec[1]*1e-9

def _float_to_second_nsec(value):
    sec = int(value)
    return (sec, int((value - sec)*1e9))

class PosixTimer(object):
    callback_obj = _sigev_notify_function(lambda sigval_value: ctypes.cast(sigval_value.sival_ptr, ctypes.py_object).value.callback())

    def __init__(self, clockid):
        super(PosixTimer,self).__init__()
        self.timerid = ctypes.c_void_p(0)
        ev = _Struct_sigevent()
        ev.sigev_signo = 0
        ev.sigev_value.sival_ptr = ctypes.c_void_p.from_buffer(ctypes.py_object(self))
        ev.sigev_notify = _SIGEV_THREAD
        ev.sigev_notify_function = self.callback_obj
        ev.sigev_notify_attributes = None
        _librt.timer_create(clockid, ev, ctypes.byref(self.timerid))

    def __del__(self):
        timerid = getattr(self, "timerid", ctypes.c_void_p(0))
        if timerid:
            _librt.timer_delete(timerid)

    def set_precise(self, value_sec_nsec, interval_sec_nsec = (0,0), flags = 0):
        (value_sec, value_nsec) = value_sec_nsec
        (interval_sec, interval_nsec) = interval_sec_nsec
        setval = _Struct_itimerspec()
        retval = _Struct_itimerspec()
        setval.it_value.tv_sec = value_sec
        setval.it_value.tv_nsec = value_nsec
        setval.it_interval.tv_sec = interval_sec
        setval.it_interval.tv_nsec = interval_nsec
        _librt.timer_settime(self.timerid, flags, setval, ctypes.byref(retval))
        return ((retval.it_value.tv_sec, retval.it_value.tv_nsec), (retval.it_interval.tv_sec, retval.it_interval.tv_nsec))

    def set(self, value, interval = 0, flags = 0):
        (retvalue, retinterval) = self.set_precise(_float_to_second_nsec(value), _float_to_second_nsec(interval), flags)
        return (_second_nsec_to_float(retvalue), _second_nsec_to_float(retinterval))

    def get_precise(self):
        retval = _Struct_itimerspec()
        _librt.timer_gettime(self.timerid, ctypes.byref(retval))
        return ((retval.it_value.tv_sec, retval.it_value.tv_nsec), (retval.it_interval.tv_sec, retval.it_interval.tv_nsec))

    def get(self):
        (retvalue, retinterval) = self.get_precise()
        return (_second_nsec_to_float(retvalue), _second_nsec_to_float(retinterval))

    def getoverrun(self):
        return _librt.timer_getoverrun(self.timerid)

    def disarm_precise(self):
        return self.set_precise((0,0))

    def disarm(self):
        return self.set(0)

    def callback(self):
        pass

if __name__ == "__main__":
    import threading
    # Event will be set when we get timer callback

    class Foo(PosixTimer):
        def __init__(self, *args, **kwargs):
            super(Foo,self).__init__(*args, **kwargs)
            self.done = threading.Event()

        def callback(self):
            self.done.set()

        def wait(self, timeout=None):
            self.done.wait(timeout)

        def clear(self):
            self.done.clear()

        def did_fire(self):
            return self.done.isSet()

    foo = Foo(CLOCK_MONOTONIC)
    print(foo.set(5))

    print("It should wake in 5 seconds.")
    print(foo.get())
    print(foo.get_precise())
    foo.wait(10)
    if foo.did_fire():
        print("Woken by CLOCK_MONOTONIC!")
        foo.clear()
    else:
        print("Timed out!")
    print(foo.getoverrun())
    print(foo.set(5))

    print("It should wake in 5 seconds.")
    print(foo.get())
    print(foo.get_precise())
    print("Disarming")
    print(foo.disarm())
    foo.wait(10)
    if foo.did_fire():
        print("Woken by CLOCK_MONOTONIC!")
        foo.clear()
    else:
        print("Timed out!")
    # to test that __del__ works when refcount gets to 0
    del foo
