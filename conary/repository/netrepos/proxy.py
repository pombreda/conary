#
# Copyright (c) 2007 rPath, Inc.
#
# This program is distributed under the terms of the Common Public License,
# version 1.0. A copy of this license should have been distributed with this
# source file in a file called LICENSE. If it is not present, the license
# is always available at http://www.opensource.org/licenses/cpl.php.
#
# This program is distributed in the hope that it will be useful, but
# without any warranty; without even the implied warranty of merchantability
# or fitness for a particular purpose. See the Common Public License for
# full details.
#

import base64, itertools, os, tempfile, urllib, xmlrpclib

# a list of the protocol versions we understand. Make sure the first
# one in the list is the lowest protocol version we support and the
# last one is the current server protocol version
SERVER_VERSIONS = [ 41, 42 ]

from conary import conarycfg, trove
from conary.lib import sha1helper, tracelog, util
from conary.repository import changeset, datastore, errors, netclient
from conary.repository import transport, xmlshims
from conary.repository.netrepos import cacheset, netserver, calllog

class ProxyClient(xmlrpclib.ServerProxy):

    pass

class ProxyRepositoryServer(xmlshims.NetworkConvertors):

    publicCalls = netserver.NetworkRepositoryServer.publicCalls

    def __init__(self, cfg, basicUrl):
        self.cfg = cfg
        self.basicUrl = basicUrl
        self.logFile = cfg.logFile
        self.tmpPath = cfg.tmpDir

        self.log = tracelog.getLog(None)
        if cfg.traceLog:
            (l, f) = cfg.traceLog
            self.log = tracelog.getLog(filename=f, level=l, trace=l>2)

        if self.logFile:
            self.callLog = calllog.CallLogger(self.logFile, [])
        else:
            self.callLog = None

        self.log(1, "proxy url=%s" % basicUrl)
        self.cache = cacheset.CacheSet(self.cfg.proxyDB, self.cfg.tmpDir,
                                       self.cfg.deadlockRetry)

        self.contents = datastore.DataStore(self.cfg.proxyContentsDir)

    def callWrapper(self, protocol, port, methodname, authToken, args,
                    remoteIp = None, rawUrl = None):
        if methodname not in self.publicCalls:
            return (False, True, ("MethodNotSupported", methodname, ""))

        self._port = port
        self._protocol = protocol

        # simple proxy. FIXME: caching these might help; building all
        # of this framework for every request seems dumb. it seems like
        # we could get away with one total since we're just changing
        # hostname/username/entitlement

        url = rawUrl

        # paste in the user/password info
        s = url.split('/')
        s[2] = ('%s:%s@' % (netclient.quote(authToken[0]),
                            netclient.quote(authToken[1]))) + s[2]
        url = '/'.join(s)

        if authToken[2] is not None:
            entitlement = authToken[2:4]
        else:
            entitlement = None

        transporter = transport.Transport(https = url.startswith('https:'),
                                          entitlement = entitlement)

        transporter.setCompress(True)
        proxy = ProxyClient(url, transporter)

        if hasattr(self, methodname):
            # handled internally
            method = self.__getattribute__(methodname)

            if self.callLog:
                self.callLog.log(remoteIp, authToken, methodname, args)

            try:
                anon, r = method(proxy, authToken, *args)
            except ProxyRepositoryError, e:
                return (False, True, e.args)

            return (anon, False, r)

        return self._proxyCall(proxy, methodname, args)

    @staticmethod
    def _proxyCall(proxy, methodname, args):
        try:
            rc = proxy.__getattr__(methodname)(*args)
        except IOError, e:
            return [ False, True, [ 'ProxyError', e.strerror[1] ] ]
        except xmlrpclib.ProtocolError, e:
            if e.errcode == 403:
                raise errors.InsufficientPermission

            raise

        return rc

    def _reposCall(self, proxy, methodname, args):
        rc = self._proxyCall(proxy, methodname, args)
        if rc[1]:
            # exception occured
            raise ProxyRepositoryError(rc[2])

        return (rc[0], rc[2])

    def urlBase(self):
        return self.basicUrl % { 'port' : self._port,
                                 'protocol' : self._protocol }

    def checkVersion(self, proxy, authToken, clientVersion):
        self.log(2, authToken[0], "clientVersion=%s" % clientVersion)
        # cut off older clients entirely, no negotiation
        if clientVersion < SERVER_VERSIONS[0]:
            raise errors.InvalidClientVersion(
               'Invalid client version %s.  Server accepts client versions %s '
               '- read http://wiki.rpath.com/wiki/Conary:Conversion' %
               (clientVersion, ', '.join(str(x) for x in SERVER_VERSIONS)))

        useAnon, parentVersions = self._reposCall(proxy, 'checkVersion',
                                                  [ clientVersion ])

        return useAnon, sorted(list(set(SERVER_VERSIONS) & set(parentVersions)))

    def _cvtJobEntry(self, authToken, jobEntry):
        (name, (old, oldFlavor), (new, newFlavor), absolute) = jobEntry

        newVer = self.toVersion(new)

        if old == 0:
            l = (name, (None, None),
                       (self.toVersion(new), self.toFlavor(newFlavor)),
                       absolute)
        else:
            l = (name, (self.toVersion(old), self.toFlavor(oldFlavor)),
                       (self.toVersion(new), self.toFlavor(newFlavor)),
                       absolute)
        return l

    def getChangeSet(self, proxy, authToken, clientVersion, chgSetList, recurse,
                     withFiles, withFileContents, excludeAutoSource):
        pathList = []
        allTrovesNeeded = []
        allFilesNeeded = []
        allTrovesRemoved = []
        allSizes = []

        csVersion = netserver.NetworkRepositoryServer._getChangeSetVersion(
                                                                clientVersion)

        for rawJob in chgSetList:
            job = self._cvtJobEntry(authToken, rawJob)

            cacheEntry = self.cache.getEntry(job, recurse, withFiles,
                                     withFileContents, excludeAutoSource,
                                     csVersion)
            path = None

            if cacheEntry is not None:
                path, (trovesNeeded, filesNeeded, removedTroves, sizes), \
                        size = cacheEntry
                invalidate = False

                # revalidate the cache entries for both permissions and
                # currency
                troveList = []
                cs = changeset.ChangeSetFromFile(path)
                for trvCs in cs.iterNewTroveList():
                    troveList.append(
                            ((trvCs.getName(), trvCs.getNewVersion(),
                              trvCs.getNewFlavor()),
                              trvCs.getNewSigs().freeze()))

                fetchList = [ (x[0][0], self.fromVersion(x[0][1]),
                               self.fromFlavor(x[0][2]) ) for x in troveList ]
                serverSigs = self._reposCall(proxy, 'getTroveInfo',
                            [ clientVersion, trove._TROVEINFO_TAG_SIGS,
                              fetchList ] )[1]
                for (troveInfo, cachedSigs), (present, reposSigs) in \
                                    itertools.izip(troveList, serverSigs):
                    if present < 1 or \
                                not cachedSigs or \
                                cachedSigs != base64.decodestring(reposSigs):
                        invalidate = True
                        break

                if invalidate:
                    self.cache.invalidateEntry(None, job[0], job[2][0],
                                               job[2][1])
                    path = None

            if path is None:
                url, sizes, trovesNeeded, filesNeeded, removedTroves = \
                    self._reposCall(proxy, 'getChangeSet',
                            [ clientVersion, [ rawJob ], recurse, withFiles,
                              withFileContents, excludeAutoSource ] )[1]

                (fd, tmpPath) = tempfile.mkstemp(dir = self.cache.tmpDir,
                                                 suffix = '.tmp')
                dest = os.fdopen(fd, "w")
                size = util.copyfileobj(urllib.urlopen(url), dest)
                dest.close()

                (key, path) = self.cache.addEntry(job, recurse, withFiles,
                                    withFileContents, excludeAutoSource,
                                    (trovesNeeded, filesNeeded, removedTroves,
                                     sizes), size = size, csVersion = csVersion)

                os.rename(tmpPath, path)

            pathList.append((path, size))
            allTrovesNeeded += trovesNeeded
            allFilesNeeded += filesNeeded
            allTrovesRemoved += removedTroves
            allSizes += sizes

        (fd, path) = tempfile.mkstemp(dir = self.cfg.tmpDir, suffix = '.cf-out')
        url = os.path.join(self.urlBase(),
                           "changeset?%s" % os.path.basename(path[:-4]))
        f = os.fdopen(fd, 'w')

        for path, size in pathList:
            f.write("%s %d\n" % (path, size))

        f.close()

        return False, (url, allSizes, allTrovesNeeded, allFilesNeeded, 
                      allTrovesRemoved)

    def getFileContents(self, proxy, authToken, clientVersion, fileList,
                        authCheckOnly = False):
        if clientVersion < 42:
            # server doesn't support auth checks through getFileContents
            return self._reposCall(proxy, 'getFileContents',
                                   [ clientVersion, fileList, authCheckOnly ])

        hasFiles = []
        neededFiles = []

        for encFileId, encVersion in fileList:
            fileId = sha1helper.sha1ToString(self.toFileId(encFileId))
            if self.contents.hasFile(fileId + '-c'):
                path = self.contents.hashToPath(fileId + '-c')
                try:
                    # touch the file; we don't want it to be removed
                    # by a cleanup job when we need it
                    os.open(path, os.O_RDONLY)
                    hasFiles.append((encFileId, encVersion))
                    continue
                except OSError:
                    pass

            neededFiles.append((encFileId, encVersion))

        # make sure this user has permissions for these file contents. an
        # exception will get raised if we don't have sufficient permissions
        if hasFiles:
            self._reposCall(proxy, 'getFileContents',
                    [ clientVersion, hasFiles, True ])

        if neededFiles:
            # now get the contents we don't have cached
            (url, sizes) = self._reposCall(proxy, 'getFileContents',
                    [ clientVersion, neededFiles, False ])[1]

            (fd, tmpPath) = tempfile.mkstemp(dir = self.cache.tmpDir,
                                             suffix = '.tmp')
            dest = os.fdopen(fd, "w+")
            size = util.copyfileobj(urllib.urlopen(url), dest)
            dest.seek(0)

            totalSize = sum(sizes)
            start = 0

            # We skip the integrity check here because (1) the hash we're using
            # has '-c' applied and (2) the hash is a fileId sha1, not a file
            # contents sha1
            for (encFileId, envVersion), size in itertools.izip(neededFiles,
                                                                sizes):
                fileId = sha1helper.sha1ToString(self.toFileId(encFileId))
                nestedF = util.SeekableNestedFile(dest, size, start)
                self.contents.addFile(nestedF, fileId + '-c',
                                      precompressed = True,
                                      integrityCheck = False)
                totalSize -= size
                start += size

        (fd, path) = tempfile.mkstemp(dir = self.tmpPath,
                                      suffix = '.cf-out')
        sizeList = []

        try:
            for encFileId, encVersion in fileList:
                fileId = sha1helper.sha1ToString(self.toFileId(encFileId))
                filePath = self.contents.hashToPath(fileId + '-c')
                size = os.stat(filePath).st_size
                sizeList.append(size)
                os.write(fd, "%s %d\n" % (filePath, size))

            url = os.path.join(self.urlBase(),
                               "changeset?%s" % os.path.basename(path)[:-4])
            return False, (url, sizeList)
        finally:
            os.close(fd)

class ProxyRepositoryError(Exception):

    def __init__(self, args):
        self.args = args