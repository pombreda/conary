#
# Copyright (c) 2004 Specifix, Inc.
#
# This program is distributed under the terms of the Common Public License,
# version 1.0. A copy of this license should have been distributed with this
# source file in a file called LICENSE. If it is not present, the license
# is always available at http://www.opensource.org/licenses/cpl.php.
#
# This program is distributed in the hope that it will be useful, but
# without any waranty; without even the implied warranty of merchantability
# or fitness for a particular purpose. See the Common Public License for
# full details.
#

"""
Provides a data storage mechanism for files which are indexed by a hash
index.

The hash can be any arbitrary string of at least 5 bytes in length;
keys are assumed to be unique.
"""

import errno
import fcntl
import gzip
from lib import log
import os
import struct
from lib import util

class DataStore:

    def hashToPath(self, hash):
	if (len(hash) < 5):
	    raise KeyError, ("invalid hash %s" % hash)

	return os.sep.join((self.top, hash[0:2], hash[2:4], hash[4:]))

    def hasFile(self, hash):
	path = self.hashToPath(hash)
	return os.path.exists(path)

    def decrementCount(self, path):
	"""
	Decrements the count by one; it it becomes 1, the count file
	is removed. If it becomes zero, the contents are removed.
	"""
        countPath = path + "#"

	# use the count file for locking, *even if it doesn't exist*
        # first ensure that the directory exists
        self.makeDir(path)
	countFile = os.open(countPath, os.O_RDWR | os.O_CREAT)
	fcntl.lockf(countFile, fcntl.LOCK_EX)
        
	val = os.read(countFile, 100)
	if not val:
	    # no count file, remove the file
            try:
                os.unlink(path)
            except OSError, e:
                if e.errno == errno.ENOENT:
                    # the contents have already been erased
                    log.warning("attempted to remove %s from the data store, but it was missing", path)
                else:
                    raise
	    # someone may try to recreate the file in here, but it should
	    # work fine. even if multiple processes try to, one will create
	    # the file and the rest will block on the countFile. once
	    # we unlink it, everything will get moving again.
	    os.unlink(countPath)
	else:
	    val = int(val[:-1])
	    if val == 1:
		os.unlink(countPath)
	    else:
		val -= 1
		os.lseek(countFile, 0, 0)
		os.ftruncate(countFile, 0)
		os.write(countFile, "%d\n" % val)

	os.close(countFile)

    def incrementCount(self, path, fileObj = None):
	"""
	Increments the count by one.  it becomes one, the contents
	of fileObj are stored into that path.
	"""
        countPath = path + "#"

        self.makeDir(path)
	if os.path.exists(path):
	    # if the path exists, it must be correct since we move the
	    # contents into place atomicly. all we need to do is
	    # increment the count
	    countFile = os.open(countPath, os.O_RDWR | os.O_CREAT)
	    fcntl.lockf(countFile, fcntl.LOCK_EX)

	    val = os.read(countFile, 100)
	    if not val:
		val = 0
	    else:
		val = int(val[:-1])

	    val += 1
	    os.lseek(countFile, 0, 0)
	    os.ftruncate(countFile, 0)
	    os.write(countFile, "%d\n" % val)
	    os.close(countFile)
	else:
	    # new file, try to be the one who creates it
	    newPath = path + ".new"

	    fd = os.open(newPath, os.O_RDWR | os.O_CREAT)

	    # get a write lock on the file
	    fcntl.lockf(fd, fcntl.LOCK_EX)

	    # if the .new file doesn't exist anymore, someone else must
	    # have gotten the write lock before we did, created the
	    # file, and then moved it into place. when this happens
	    # we need to update the count instead
	    
	    if not os.path.exists(newPath):
		os.close(fd)
		return self.incrementCount(path, fileObj = fileObj)

	    fObj = os.fdopen(fd, "r+")
	    dest = gzip.GzipFile(mode = "w", fileobj = fObj)
	    util.copyfileobj(fileObj, dest)
	    os.rename(newPath, path)

	    dest.close()
	    # this closes fd for us
	    fObj.close()

    def readCount(self, path):
        # XXX this code is not used anymore
	if os.path.exists(path + "#"):
	    fd = os.open(path + "#", os.O_RDONLY)
            fcntl.lockf(fd, fcntl.LOCK_SH)
            f = os.fdopen(fd)
	    # cut off the trailing \n
	    count = int(f.read()[:-1])
            os.close(fd)
	elif os.path.exists(path):
	    count = 1
	else:
	    count = 0

	return count

    # add one to the reference count for a file which already exists
    # in the archive
    def addFileReference(self, hash):
	path = self.hashToPath(hash)
	self.incrementCount(path)

    def makeDir(self, path):
        d = os.path.dirname(path)
	shortPath = d[:-3]

        for _dir in (shortPath, d):
            try:
                os.mkdir(_dir)
            except OSError, e:
                if e.errno != errno.EEXIST:
                    raise

    # file should be a python file object seek'd to the beginning
    # this messes up the file pointer
    def addFile(self, f, hash):
	path = self.hashToPath(hash)
        self.makeDir(path)
	self.incrementCount(path, fileObj = f)

    # returns a python file object for the file requested
    def openFile(self, hash, mode = "r"):
	path = self.hashToPath(hash)
	f = open(path, "r")

	gzfile = gzip.GzipFile(path, mode)
	gzfile.fullSize = util.gzipFileSize(f)
	return gzfile

    # returns a python file object for the file requested
    def openRawFile(self, hash):
	path = self.hashToPath(hash)
	f = open(path, "r")
	return f

    def removeFile(self, hash):
	path = self.hashToPath(hash)
	self.decrementCount(path)

	try:
            # XXX remove the next level up as well
	    os.rmdir(os.path.dirname(path))
	except OSError:
	    # if this fails there are probably just other files
	    # in that directory; just ignore it
	    pass

    def __init__(self, topPath):
	self.top = topPath
	if (not os.path.isdir(self.top)):
	    raise IOError, ("path is not a directory: %s" % topPath)
