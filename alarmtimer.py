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
import os
import threading
import sys

# C libraries
libc = ctypes.CDLL("libc.so.6")
librt = ctypes.CDLL("librt.so", use_errno=True)

# Most of the stuff here is all the structs and types required to make this 
# work with ctypes. Basically this is all taken straight out of bits/siginfo.h 
# on Linux and thus is highly non-portable and otherwise a really bad idea.
#
# ... but it does let you do it from Python. ;)

# Types
clockid_t = ctypes.c_int32
pid_t = ctypes.c_int32
timer_t = ctypes.c_void_p
time_t = ctypes.c_long

# Clock IDs
CLOCK_REALTIME_ALARM = clockid_t(8)

# Notification IDs
SIGEV_SIGNAL = ctypes.c_int(0)
SIGEV_NONE = ctypes.c_int(1)
SIGEV_THREAD = ctypes.c_int(2)


# The sigval union from <signal.h>
class Union_sigval(ctypes.Union):
    _fields_ = [
        ("sival_int", ctypes.c_int),
        ("sival_ptr", ctypes.c_void_p),
    ]


# The SIGEV_THREAD callback funtion type
sigev_notify_function = ctypes.CFUNCTYPE(None, Union_sigval)


# The sigevent structure from <signal.h>
class Struct__sigev_thread(ctypes.Structure):
    _fields_ = [
        ("sigev_notify_function", sigev_notify_function),
        ("sigev_notify_attributes", ctypes.c_void_p),
    ]


class Struct__sigev_un(ctypes.Union):
    _anonymous_ = ("_sigev_thread", )
    _fields_ = [
        ("_pad", ctypes.c_int * 13), # or 12 on 64-bit...
        ("_tid", pid_t),
        ("_sigev_thread", Struct__sigev_thread),
    ]


class Struct_sigevent(ctypes.Structure):
    _anonymous_ = ("_sigev_un", )
    _fields_ = [
        ("sigev_value", Union_sigval),
        ("sigev_signo", ctypes.c_int),
        ("sigev_notify", ctypes.c_int),
        ("_sigev_un", Struct__sigev_un),
    ]

# The timespec struct from <time.h>
class Struct_timespec(ctypes.Structure):
    _fields_ = [
        ("tv_sec", time_t),
        ("tv_nsec", ctypes.c_long)
    ]

# The itimerspec struct from <time.h>
class Struct_itimerspec(ctypes.Structure):
    _fields_ = [
        ("it_interval", Struct_timespec),  # Interval for periodic timer
        ("it_value", Struct_timespec),  # First expiration
    ]


if __name__ == "__main__":
    # Event will be set when we get timer callback
    done = threading.Event()

    # Callback function
    def callback(sigval_value):
        done.set()

    # How we signal the event
    ev = Struct_sigevent()
    ev.sigev_signo = 0
    ev.sigev_notify = SIGEV_THREAD
    ev.sigev_notify_function = sigev_notify_function(callback)
    ev.sigev_notify_attributes = None

    # Create a new POSIX Alarm Timer
    timerid = ctypes.c_int(0)
    ret = librt.timer_create(CLOCK_REALTIME_ALARM, ctypes.byref(ev),
            ctypes.byref(timerid))
    if ret == -1:
        errnum = ctypes.get_errno()
        print("ERROR: timer_create: %s"%(os.strerror(errnum)))
        if errnum == errno.EPERM:
            print("You probably aren't root or someone with CAP_WAKE_ALARM")
            print("Maybe try `sudo ./alarmtimer.py`")
        elif errnum == errno.EINVAL:
            print("This system might not support CLOCK_REALTIME_ALARM")
        sys.exit(1)

    # Get the current time...
    value = Struct_itimerspec()
    ret = librt.clock_gettime(CLOCK_REALTIME_ALARM, 
            ctypes.byref(value.it_value))
    if ret == -1:
        print("ERROR: clock_gettime: %s"%(os.strerror(ctypes.get_errno())))
        sys.exit(1)

    # ...add 1 minute too it...
    value.it_interval.tv_sec = 0
    value.it_interval.tv_nsec = 0
    value.it_value.tv_sec += 60
    value.it_value.tv_nsec = 0

    # ...and use it to arm a our timer.
    ret = librt.timer_settime(timerid, 0x0, ctypes.byref(value), None)
    if ret == -1:
        print("ERROR: timer_settime: %s"%(os.strerror(ctypes.get_errno())))
        sys.exit(1)

    print("Please suspend your computer... It should wake in 1 minute.")
    done.wait()
    print("Woken by CLOCK_REALTIME_ALARM!")
