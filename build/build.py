#
# Copyright (c) 2004 Specifix, Inc.
# All rights reserved
#
"""
Module used by recipes to direct the build and installation of
software packages.  Classes from this module are not used directly;
instead, they are used through eponymous interfaces in recipe.

@var _permmap: A mapping of common integer file modes to their octal
equivalents.  This is used to check for common mistakes when specifying
the permissions on files in classes derived from _PutFile.
"""

import os
import util
import string
import fixedglob
import log

# make sure that the decimal value really is unreasonable before
# adding a new translation to this file.
_permmap = {
    1755: 01755,
    2755: 02755,
    4755: 04755,
    755: 0755,
    750: 0750,
    644: 0644,
    640: 0640,
}

class BuildAction(util.Action):
    keywords = {
        'use': None
    }
    def __init__(self, *args, **keywords):
	"""
	@keyword use: Optional argument; Use flag(s) telling whether
	to actually perform the action.
	@type use: None, Use flag, or sequence of Use flags
	"""
	# enforce pure virtual status
        assert(self.__class__ is not BuildCommand)
	util.Action.__init__(self, *args, **keywords)
	# change self.use to be a simple flag
	self.use = util.checkUse(self.use)

    def doBuild(self, recipe):
	self.recipe = recipe
	if self.use:
	    self.do(recipe.macros)

class BuildCommand(BuildAction, util.ShellCommand):
    """
    Pure virtual class which implements the do method,
    based on the shell command built from a template.
    """
    def __init__(self, *args, **keywords):
	# enforce pure virtual status
        assert(self.__class__ is not BuildCommand)
	BuildAction.__init__(self, *args, **keywords)
	util.ShellCommand.__init__(self, *args, **keywords)

    def do(self, macros):
        """
	Method which is used if the ShellCommand instance is invoked 
        during build
        @param macros: macros which will be expanded through dictionary
        substitution in self.command
        @type macros: recipe.Macros
        @return: None
        @rtype: None
	"""
        util.execute(self.command %macros)


class Run(BuildCommand):
    """
    Just run a command with simple macro substitution
    """
    template = "%(args)s"


class Automake(BuildCommand):
    # note: no use of %(args)s -- which command would it apply to?
    template = ('cd %%(builddir)s/%(subDir)s; '
                'aclocal %%(m4DirArgs)s %(acLocalArgs)s; '
		'%(preAutoconf)s autoconf %(autoConfArgs)s; '
		'automake%(automakeVer)s %(autoMakeArgs)s')
    keywords = {'autoConfArgs': '',
                'autoMakeArgs': '',
		'acLocalArgs': '',
		'preAutoconf': '',
                'm4Dir': '',
		'automakeVer': '',
                'subDir': ''}
    
    def do(self, macros):
	macros = macros.copy()
        if self.m4Dir:
	    macros.update({'m4DirArgs': '-I %s' %(self.m4Dir)})
        util.execute(self.command %macros)


class Configure(BuildCommand):
    """The Configure class runs an autoconf configure script with the
    default paths as defined by the macro set passed into it when doBuild
    is invoked.  It provides many common arguments, set correctly to
    values provided by system macros.  If any of these arguments do
    not work for a program, then use the ManualConfigure class instead.
    """
    # note that template is NOT a tuple, () is used merely to group strings
    # to avoid trailing \ characters on every line
    template = (
	'cd %%(builddir)s; '
	'%%(mkObjdir)s '
	'%%(cdSubDir)s '
	'CFLAGS="%%(cflags)s" CXXFLAGS="%%(cflags)s"'
	' %(preConfigure)s %%(configure)s'
	# XXX host/build/target here
	' --prefix=%%(prefix)s'
	' --exec-prefix=%%(exec_prefix)s'
	' --bindir=%%(bindir)s'
	' --sbindir=%%(sbindir)s'
	' --sysconfdir=%%(sysconfdir)s'
	' --datadir=%%(datadir)s'
	' --includedir=%%(includedir)s'
	' --libdir=%%(libdir)s'
	' --libexecdir=%%(libexecdir)s'
	' --localstatedir=%%(localstatedir)s'
	' --sharedstatedir=%%(sharedstatedir)s'
	' --mandir=%%(mandir)s'
	' --infodir=%%(infodir)s'
	'  %(args)s')
    keywords = {'preConfigure': '',
                'objDir': '',
		'subDir': ''}

    def __init__(self, *args, **keywords):
        """
        Create a new Configure instance used to run the autoconf configure
        command with default parameters

        @keyword objDir: make an object directory before running configure.
        This is useful for applications which do not support running configure
        from the same directory as the sources (srcdir != objdir)
	@keyword subDir: relative subdirectory in which to run configure
        @keyword preConfigure: Extra shell script which is inserted in front of
        the configure command.
        """
        BuildCommand.__init__(self, *args, **keywords)
         
    def do(self, macros):
	macros = macros.copy()
        if self.objDir:
            macros['mkObjdir'] = 'mkdir -p %s; cd %s;' \
	                         %(self.objDir, self.objDir)
	    macros['configure'] = '../configure'
        else:
            macros['configure'] = './configure'
	if self.subDir:
	    macros['cdSubDir'] = 'cd %s;' %self.subDir
        util.execute(self.command %macros)

class ManualConfigure(Configure):
    """
    The ManualConfigure class works exactly like the configure class,
    except that all the arguments to the configure script have to be
    provided explicitly.
    """
    template = ('cd %%(builddir)s/%(subDir)s; '
                '%%(mkObjdir)s '
	        '%(preConfigure)s %%(configure)s %(args)s')

class Make(BuildCommand):
    """
    The Make class runs the make utility with CFLAGS and CXXFLAGS set
    to system defaults, with system default for mflags and parallelmflags.
    This means, among other things, that if your package does not build
    correctly with parallelized make, you should disable parallel
    make by using self.disableParallelMake() in your recipe.  If your
    package can do parallel builds but needs some other mechanism,
    then you can modify parallelmflags as necessary in your recipe.
    """
    template = ('cd %%(builddir)s/%(subDir)s; '
	        'CFLAGS="%%(cflags)s" CXXFLAGS="%%(cflags)s"'
                ' %(preMake)s make %%(mflags)s %%(parallelmflags)s %(args)s')
    keywords = {'preMake': '',
                'subDir': ''}

class MakeParallelSubdir(Make):
    """
    The MakeParallelSubdir class runs the make utility with CFLAGS
    and CXXFLAGS set to system defaults, with system default for
    parallelmflags only applied to sub-make processes.
    """
    template = ('cd %%(builddir)s/%(subDir)s; '
	        'CFLAGS="%%(cflags)s" CXXFLAGS="%%(cflags)s"'
                ' %(preMake)s make %%(mflags)s '
                ' MAKE="make %%(mflags)s %%(parallelmflags)s" %(args)s')

class MakeInstall(Make):
    """
    The MakeInstall class is like the Make class, except that it
    automatically sets DESTDIR.  If your package does not have
    DESTDIR or an analog, use the MakePathsInstall class instead,
    or as a last option, the Make class.
    """
    template = ('cd %%(builddir)s/%(subDir)s; '
	        'CFLAGS="%%(cflags)s" CXXFLAGS="%%(cflags)s"'
                ' %(preMake)s make %%(mflags)s %%(rootVarArgs)s'
		' %(installtarget)s %(args)s')
    keywords = {'rootVar': 'DESTDIR',
		'installtarget': 'install'}

    def do(self, macros):
	macros = macros.copy()
        if self.rootVar:
	    macros.update({'rootVarArgs': '%s=%s'
	                  %(self.rootVar, macros['destdir'])})
	util.execute(self.command %macros)

class MakePathsInstall(Make):
    """
    The MakePathsInstall class is used when there is no single functional
    DESTDIR or similar definition, but enough of the de-facto standard 
    variables (prefix, bindir, etc) are honored by the Makefile to make
    a destdir installation successful.
    """
    template = (
	'cd %%(builddir)s/%(subDir)s; '
	'CFLAGS="%%(cflags)s" CXXFLAGS="%%(cflags)s"'
	' %(preMake)s make %%(mflags)s'
	' prefix=%%(destdir)s/%%(prefix)s'
	' exec-prefix=%%(destdir)s/%%(exec_prefix)s'
	' bindir=%%(destdir)s/%%(bindir)s'
	' sbindir=%%(destdir)s/%%(sbindir)s'
	' sysconfdir=%%(destdir)s/%%(sysconfdir)s'
	' datadir=%%(destdir)s/%%(datadir)s'
	' includedir=%%(destdir)s/%%(includedir)s'
	' libdir=%%(destdir)s/%%(libdir)s'
	' libexecdir=%%(destdir)s/%%(libexecdir)s'
	' localstatedir=%%(destdir)s/%%(localstatedir)s'
	' sharedstatedir=%%(destdir)s/%%(sharedstatedir)s'
	' mandir=%%(destdir)s/%%(mandir)s'
	' infodir=%%(destdir)s/%%(infodir)s'
	' %(installtarget)s %(args)s')
    keywords = {'installtarget': 'install'}



class InstallDesktopfile(BuildCommand):
    """
    The InstallDesktopfile class should be used to provide categories
    (and vendor, if necessary) for files in /usr/share/applications/
    """
    template = ('desktop-file-install --vendor %(vendor)s'
		' --dir %%(destdir)s/%%(datadir)s/applications'
		' %%(category)s'
		' %(args)s')
    keywords = {'vendor': 'net',
		'categories': None}

    def doBuild(self, recipe):
	macros = recipe.macros.copy()
        if self.categories:
	    macros['category'] = '--add-category %s' %self.categories
	BuildCommand.doBuild(self, macros)


class _FileAction(BuildAction):
    def chmod(self, destdir, path):
	if self.mode >= 0:
	    os.chmod(destdir+os.sep+path, self.mode & 01777)
	    if self.mode & 06000:
		self.recipe.fixmodes[path] = self.mode
	
class SetModes(_FileAction):
    """
    In order for a file to be setuid in the repository, it needs to
    have its mode explicitly provided in the recipe.  If any file
    installation class that provides a mode is used, that will be
    sufficient, but for files that are installed by makefiles, a
    specific, intentional listing of their mode must be provided.
    The SetModes class provides the mechanism for that.

    In addition, of course, it can be used to change arbitrary
    file modes in the destdir.
    """
    def __init__(self, path, mode, use=None):
	self.mode = mode
	if type(path) is str:
	    path = (path,)
	self.paths = path
	self.use = util.checkUse(use)

    def do(self, macros):
	files = []
	for path in self.paths:
	    files.extend(util.braceExpand(path %macros))
	for f in files:
	    log.debug('changing mode for %s to %o' %(f, self.mode))
	    self.chmod(macros['destdir'], f)

class _PutFiles(_FileAction):
    def do(self, macros):
	dest = macros['destdir'] + self.toFile %macros
	destlen = len(macros['destdir'])
	util.mkdirChain(os.path.dirname(dest))

	for fromFile in self.fromFiles:
	    sources = (self.source + fromFile) %macros
	    sourcelist = util.braceGlob(sources)
	    if not os.path.isdir(dest) and len(sourcelist) > 1:
		raise TypeError, 'multiple files specified, but destination "%s" is not a directory'
	    for source in sourcelist:
		thisdest = dest
                if os.path.isdir(dest):
		    thisdest = dest + os.path.basename(source)

		if self.move:
		    util.rename(source, thisdest)
		else:
		    util.copyfile(source, thisdest)

		if self.mode >= 0:
		    self.chmod(macros['destdir'], thisdest[destlen:])

    def __init__(self, fromFiles, toFile, mode, use):
	self.toFile = toFile
	if type(fromFiles) is str:
	    self.fromFiles = (fromFiles,)
	else:
	    self.fromFiles = fromFiles
	# notice obviously broken permissions
	if mode >= 0:
	    if _permmap.has_key(mode):
                log.warning('odd permission %o, correcting to %o: add initial "0"?' \
                            %(mode, _permmap[mode]))
		mode = _permmap[mode]
	self.mode = mode
	self.use = util.checkUse(use)
    

class InstallFiles(_PutFiles):
    """
    This class installs files from the builddir to the destdir.
    """
    def __init__(self, fromFiles, toFile, mode = 0644, use=None):
	_PutFiles.__init__(self, fromFiles, toFile, mode, use)
	self.source = ''
	self.move = 0

class MoveFiles(_PutFiles):
    """
    This class moves files within the destdir.
    """
    def __init__(self, fromFiles, toFile, mode = -1, use=None):
	_PutFiles.__init__(self, fromFiles, toFile, mode, use)
	self.source = '%(destdir)s'
	self.move = 1

class InstallSymlinks(BuildAction):
    """
    The InstallSymlinks class create symlinks.  Multiple symlinks
    can be created if the destination path is a directory.  The
    destination path is determined to be a directory if it already
    exists or if the path ends with the directory separator character
    ("/" on UNIX systems)
    """
    def do(self, macros):
	dest = macros['destdir'] + self.toFile %macros

        if dest.endswith(os.sep):
            util.mkdirChain(dest)
        else:
            util.mkdirChain(os.path.dirname(dest))

        targetIsDir = os.path.isdir(dest)
        if targetIsDir:
            destdir = dest
        else:
            destdir = os.path.dirname(dest)

        if type(self.fromFiles) is str:
            self.fromFiles = (self.fromFiles,)

        sources = []
        for fromFile in self.fromFiles:
            sources.extend(util.braceExpand(fromFile %macros))

        # do glob expansion and path verification on all of the source paths
        expandedSources = []
        for source in sources:
            # if the symlink contains a /, concatenate in order to glob
            if source.startswith(os.sep):
                expand = macros['destdir'] + source
            else:
                expand = destdir + os.sep + source
            sources = fixedglob.glob(expand)
            if not sources and not self.allowDangling:
                raise TypeError, 'symlink to "%s" would be dangling' %source
            for expanded in sources:
                if os.sep in source:
                    expandedSources.append(os.path.dirname(source) + os.sep +
                                           os.path.basename(expanded))
                else:
                    expandedSources.append(os.path.basename(expanded))
        sources = expandedSources
        
        if len(sources) > 1 and not targetIsDir:
            raise TypeError, 'creating multiple symlinks, but destination is not a directory'

        for source in sources:
            if targetIsDir:
                to = dest + os.sep + os.path.basename(source)
            else:
                to = dest
	    if os.path.exists(to) or os.path.islink(to):
		os.remove(to)
            log.debug('creating symlink %s -> %s' %(to, source))
	    os.symlink(os.path.normpath(source), to)

    def __init__(self, fromFiles, toFile, use=None, allowDangling=False):
        """
        Create a new InstallSymlinks instance

        @param fromFiles: paths(s) to which symlink(s) will be created
        @type fromFiles: str or sequence of str
        @param toFile: path to create the symlink, or a directory in which
                       to create multiple symlinks
        @type toFile: str
	@param use: Optional argument; Use flag(s) telling whether
	to actually perform the action.
	@type use: None, Use flag, or sequence of Use flags
        @param allowDangling: Optional argument; set to True to allow the
        creation of dangling symlinks
        @type allowDangling: bool
        """
	# raise error early
	if type(fromFiles) is not str:
	    if not toFile.endswith('/') or os.path.isdir(toFile):
		raise TypeError, 'too many targets for non-directory %s' %toFile
	self.fromFiles = fromFiles
	self.toFile = toFile
	self.use = util.checkUse(use)
        self.allowDangling = allowDangling

class RemoveFiles(BuildAction):
    """
    The RemoveFiles class removes files from within the destdir
    """
    def do(self, macros):
	for filespec in self.filespecs:
	    if self.recursive:
		util.rmtree("%s/%s" %(macros['destdir'], filespec %macros))
	    else:
		util.remove("%s/%s" %(macros['destdir'], filespec %macros))

    def __init__(self, filespecs, recursive=0, use=None):
	if type(filespecs) is str:
	    self.filespecs = (filespecs,)
	else:
	    self.filespecs = filespecs
	self.recursive = recursive
	self.use = util.checkUse(use)

class InstallDocs(BuildAction):
    """
    The InstallDocs class installs documentation files from the builddir
    into the destdir in the appropriate directory.
    """
    def do(self, macros):
	macros = macros.copy()
	if self.subdir:
	    macros['subdir'] = '/%s' % self.subdir
	if self.devel:
	    dest = '%(destdir)s/%(develdocdir)s/%(name)s-%(version)s/%(subdir)s/' %macros
	else:
	    dest = '%(destdir)s/%(docdir)s/%(name)s-%(version)s/%(subdir)s/' %macros
	util.mkdirChain(os.path.dirname(dest))
	for path in self.paths:
	    util.copytree(path, dest, True)

    def __init__(self, paths, devel=False, subdir='', use=None):
	if type(paths) is str:
	    self.paths = (paths,)
	else:
	    self.paths = paths
	self.devel = devel
	self.subdir = subdir
	self.use = util.checkUse(use)

class MakeDirs(_FileAction):
    """
    The MakeDirs class creates directories in destdir
    """
    keywords = { 'mode': 0755 }

    def do(self, macros):
        for path in self.paths:
            path = path %macros
            dirs = util.braceExpand(path)
            for d in dirs:
                d = d %macros
                dest = macros['destdir'] + d
                log.debug('creating directory %s', dest)
                util.mkdirChain(dest)
                if self.mode >= 0:
                    self.chmod(macros['destdir'], d)

    def __init__(self, paths, **keywords):
        _FileAction.__init__(self, paths, **keywords)
	if type(paths) is str:
	    self.paths = (paths,)
	else:
	    self.paths = paths
	if self.mode >= 0:
	    if _permmap.has_key(self.mode):
		log.warning('odd permission %o, correcting to %o: add initial "0"?' \
                            %(mode, _permmap[self.mode]))
		mode = _permmap[self.mode]
