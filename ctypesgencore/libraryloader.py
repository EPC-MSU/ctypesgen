# ----------------------------------------------------------------------------
# Copyright (c) 2008 David James
# Copyright (c) 2006-2008 Alex Holkner
# All rights reserved.
# 
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions 
# are met:
#
#  * Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
#  * Redistributions in binary form must reproduce the above copyright 
#    notice, this list of conditions and the following disclaimer in
#    the documentation and/or other materials provided with the
#    distribution.
#  * Neither the name of pyglet nor the names of its
#    contributors may be used to endorse or promote products
#    derived from this software without specific prior written
#    permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
# ----------------------------------------------------------------------------

import os.path, re, sys
import ctypes
import ctypes.util

def _environ_path(name):
    if name in os.environ:
        return os.environ[name].split(":")
    else:
        return []

class LibraryLoader(object):
    def __init__(self):
        self.other_dirs=[]
    
    def load_library(self,libname):
        """Given the name of a library, load it."""
        paths = self.getpaths(libname)
        
        for path in paths:
            if os.path.exists(path):
                return self.load(path)
        
        raise ImportError,"%s not found." % libname
    
    def load(self,path):
        """Given a path to a library, load it."""
        try:
            return ctypes.cdll.LoadLibrary(path)
        except OSError,e:
            raise ImportError,e
    
    def getpaths(self,libname):
        """Return a list of paths where the library might be found."""
        if os.path.isabs(libname):
            yield libname
        
        else:
            for p in self.other_dirs:
                yield os.path.join(p,libname)
            
            yield os.path.join(".",libname)
            
            path = ctypes.util.find_library(libname)
            if path: yield path
            
            for path in self.getplatformpaths(libname):
                yield path

# Darwin (Mac OS X)

class DarwinLibraryLoader(LibraryLoader):
    name_formats = ["lib%s.dylib", "lib%s.so", "lib%s.bundle", "%s.dylib",
                "%s.so", "%s.bundle", "%s"]
    
    def getplatformpaths(self,libname):
        if os.path.pathsep in libname:
            names = [libname]
        else:
            names = [format % libname for format in self.name_formats]
        
        for dir in self.getdirs(libname):
            for name in names:
                yield os.path.join(dir,name)
    
    def getdirs(self,libname):
        '''Implements the dylib search as specified in Apple documentation:
        
        http://developer.apple.com/documentation/DeveloperTools/Conceptual/
            DynamicLibraries/Articles/DynamicLibraryUsageGuidelines.html

        Before commencing the standard search, the method first checks
        the bundle's ``Frameworks`` directory if the application is running
        within a bundle (OS X .app).
        '''

        dyld_fallback_library_path = _environ_path("DYLD_FALLBACK_LIBRARY_PATH")
        if not dyld_fallback_library_path:
            dyld_fallback_library_path = [os.path.expanduser('~/lib'),
                                          '/usr/local/lib', '/usr/lib']
        
        dirs = []
        
        if hasattr(sys, 'frozen') and sys.frozen == 'macosx_app':
            dirs.append(os.path.join(
                os.environ['RESOURCEPATH'],
                '..',
                'Frameworks'))
        
        if '/' in libname:
            dirs.extend(_environ_path("DYLD_LIBRARY_PATH"))
            dirs.append(".")
            dirs.extend(dyld_fallback_library_path)
        else:
            dirs.extend(_environ_path("LD_LIBRARY_PATH"))
            dirs.extend(_environ_path("DYLD_LIBRARY_PATH"))
            dirs.append(".")
            dirs.extend(dyld_fallback_library_path)
        
        return dirs

# Linux

class LinuxLibraryLoader(LibraryLoader):
    _ld_so_cache = None
    
    def _create_ld_so_cache(self):
        # Recreate search path followed by ld.so.  This is going to be
        # slow to build, and incorrect (ld.so uses ld.so.cache, which may
        # not be up-to-date).  Used only as fallback for distros without
        # /sbin/ldconfig.
        #
        # We assume the DT_RPATH and DT_RUNPATH binary sections are omitted.

        directories = self.other_paths.copy()
        directories.append(".")
        directories.extend(_environ_path('LD_LIBRARY_PATH'))

        try: directories.extend([dir.strip() for dir in open('/etc/ld.so.conf')])
        except IOError: pass

        directories.extend(['/lib', '/usr/lib'])

        cache = {}
        lib_re = re.compile(r'lib(.*)\.so$')
        for dir in directories:
            try:
                for file in os.listdir(dir):
                    if '.so' not in file:
                        continue
                    
                    # Index by filename
                    path = os.path.join(dir, file)
                    if file not in cache:
                        cache[file] = path
                    
                    # Index by library name
                    match = lib_re.match(file)
                    if match:
                        library = match.group(1)
                        if library not in cache:
                            cache[library] = path
            except OSError:
                pass

        self._ld_so_cache = cache
    
    def getplatformpaths(self, libname):
        path = ctypes.util.find_library(libname)
        if path: yield os.path.join("/lib",path)

        if self._ld_so_cache is None:
            self._create_ld_so_cache()

        result = self._ld_so_cache.get(libname)
        if result: yield result

# Windows

class _WindowsLibrary(object):
    def __init__(self, path):
        self.cdll = ctypes.cdll.LoadLibrary(path)
        self.windll = ctypes.windll.LoadLibrary(path)

    def __getattr__(self, name):
        try: return getattr(self.cdll,name)
        except AttributeError:
            try: return getattr(self.windll,name)
            except AttributeError:
                raise

class WindowsLibraryLoader(LibraryLoader):
    name_formats = ["%s.dll", "lib%s.dll"]
    
    def load(self, path):
        return _WindowsLibrary(path)
    
    def getplatformpaths(self, libname):
        if os.path.pathsep not in libname:
            for name in self.name_formats:
                path = ctypes.util.find_library(name % libname)
                if path:
                    yield path

# Platform switching

loaderclass = {
    "darwin":   DarwinLibraryLoader,
    "cygwin":   WindowsLibraryLoader,
    "linux":    LinuxLibraryLoader,
    "win32":    WindowsLibraryLoader
}
loader = loaderclass[sys.platform]()

def add_library_search_dirs(other_dirs):
    loader.other_dirs = other_dirs

load_library = loader.load_library

del loaderclass