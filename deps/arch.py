#
# Copyright (c) 2004 Specifix, Inc.
# All rights reserved
#

import deps
import os

def flags_i686():
    ofInterest = { "cmov"   : True,
		   "mmx"    : True,
		   "sse"    : True,
		   "sse2"   : True,
		   "3dnow"  : True }
    try:
        lines = open("/proc/cpuinfo").read().split("\n")
    except IOError:
        lines=[]
    rc = [ 'i686' ]
    for line in lines:
	if not line.startswith("flags"): continue
	fields = line.split()
	if fields[0] != "flags": continue

	for flag in fields[2:]:
	    if ofInterest.has_key(flag): rc.append(flag)

	return deps.Dependency('x86', rc)

    return deps.Dependency('x86')

def flags_mips64():
    return deps.Dependency('mipseb', [ 'mips64' ])

def current():
    return currentArch

def any():
    return "any"

def canInstall(other):
    return other == "any" or other == currentArch

baseArch = os.uname()[4]
localNamespace = locals()
if localNamespace.has_key("flags_" + baseArch):
    currentArch = localNamespace["flags_" + baseArch]()
else:
    currentArch = deps.Dependency(baseArch)

del localNamespace
