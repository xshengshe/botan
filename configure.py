#!/usr/bin/python

"""
Configuration program for botan

Python 2.4 or higher required

(C) 2009 Jack Lloyd
Distributed under the terms of the Botan license
"""

import os
import os.path
import platform
import re
import shlex
import shutil
import sys

from optparse import OptionParser, SUPPRESS_HELP
from string import Template

from getpass import getuser
from time import ctime

class BuildConfigurationInformation(object):

    def __init__(self, options, modules):
        self.checkobj_dir = os.path.join(options.build_dir, 'checks')
        self.libobj_dir = os.path.join(options.build_dir, 'lib')

        self.include_dir = os.path.join(options.build_dir, 'include')
        self.full_include_dir = os.path.join(self.include_dir, 'botan')

        all_files = sum([mod.add for mod in modules], [])

        self.headers = sorted(
            [file for file in all_files if file.endswith('.h')])

        self.sources = sorted(set(all_files) - set(self.headers))

        self.check_sources = sorted(
            [os.path.join('checks', file) for file in
             os.listdir('checks') if file.endswith('.cpp')])

    def doc_files(self):
        docs = ['readme.txt']

        for docfile in ['api.pdf', 'tutorial.pdf', 'fips140.pdf',
                        'api.tex', 'tutorial.tex', 'fips140.tex',
                        'credits.txt', 'license.txt', 'log.txt',
                        'thanks.txt', 'todo.txt', 'pgpkeys.asc']:
            filename = os.path.join('doc', docfile)
            if os.access(filename, os.R_OK):
                docs.append(filename)
        return docs

    def version_major(self): return 1
    def version_minor(self): return 8
    def version_patch(self): return 3

    def version_so_patch(self): return 2

    def version_string(self):
        return '%d.%d.%d' % (self.version_major(),
                             self.version_minor(),
                             self.version_patch())

    def soversion_string(self):
        return '%d.%d.%d' % (self.version_major(),
                             self.version_minor(),
                             self.version_so_patch())

    def username(self):
        return getuser()

    def hostname(self):
        return platform.node()

    def timestamp(self):
        return ctime()

def process_command_line(args):
    parser = OptionParser()

    parser.add_option('--cc', dest='compiler',
                      help='set the desired build compiler')
    parser.add_option('--os', dest='os', default=platform.system().lower(),
                      help='set the target operating system [%default]')
    parser.add_option('--cpu', dest='cpu',
                      help='set the target processor type/model')

    parser.add_option('--with-build-dir', dest='build_dir',
                      metavar='DIR', default='build',
                      help='setup the build in DIR [default %default]')

    parser.add_option('--prefix', dest='prefix',
                      help='set the base installation directory')
    parser.add_option('--docdir', dest='docdir',
                      help='set the documentation installation directory')
    parser.add_option('--libdir', dest='libdir',
                      help='set the library installation directory')

    parser.add_option('--with-local-config',
                      dest='local_config', metavar='FILE',
                      help='include the contents of FILE into build.h')

    """
    These exist only for autoconf compatability (requested by zw for monotone)
    """
    compat_with_autoconf_options = [
        'bindir',
        'datadir',
        'datarootdir',
        'dvidir',
        'exec-prefix',
        'htmldir',
        'includedir',
        'infodir',
        'libexecdir',
        'localedir',
        'localstatedir',
        'mandir',
        'oldincludedir',
        'pdfdir',
        'psdir',
        'sbindir',
        'sharedstatedir',
        'sysconfdir'
        ]

    for opt in compat_with_autoconf_options:
        parser.add_option('--' + opt, dest=opt, help=SUPPRESS_HELP)

    (options, args) = parser.parse_args(args)

    return (options, args)

"""
Generic lexer function for info.txt and src/build-data files
"""
def lex_me_harder(infofile, to_obj, allowed_groups, name_val_pairs):

    class LexerError(Exception):
        def __init__(self, msg, line):
            self.msg = msg
            self.line = line

        def __str__(self):
            return '%s at %s:%d' % (self.msg, infofile, self.line)

    (dirname, basename) = os.path.split(infofile)

    to_obj.lives_in = dirname
    if basename == 'info.txt':
        (dummy,to_obj.basename) = os.path.split(dirname)
    else:
        to_obj.basename = basename

    lex = shlex.shlex(open(infofile), infofile, posix=True)

    lex.wordchars += ':.<>/,-!'

    for group in allowed_groups:
        to_obj.__dict__[group] = []
    for (key,val) in name_val_pairs.iteritems():
        to_obj.__dict__[key] = val

    def lexed_tokens(): # Convert to an interator
        token = lex.get_token()
        while token != None:
            yield token
            token = lex.get_token()

    for token in lexed_tokens():
        match = re.match('<(.*)>', token)

        # Check for a grouping
        if match is not None:
            group = match.group(1)

            if group not in allowed_groups:
                raise LexerError('Unknown group "%s"' % (group), lex.lineno)

            end_marker = '</' + group + '>'

            token = lex.get_token()
            while token != None and token != end_marker:
                to_obj.__dict__[group].append(token)
                token = lex.get_token()
        elif token in name_val_pairs.keys():
            to_obj.__dict__[token] = lex.get_token()
        else: # No match -> error
            raise LexerError('Bad token "%s"' % (token), lex.lineno)

"""
Convert a lex'ed map (from build-data files) from a list to a dict
"""
def force_to_dict(l):
    return dict(zip(l[::3],l[2::3]))

"""
Represents the information about a particular module
"""
class ModuleInfo(object):
    def __init__(self, infofile):

        lex_me_harder(infofile, self,
                      ['add', 'requires', 'os', 'arch', 'cc', 'libs'],
                      { 'realname': '<UNKNOWN>',
                        'load_on': 'request',
                        'define': None,
                        'modset': None,
                        'uses_tr1': 'false',
                        'note': '',
                        'mp_bits': 0 })

        # Coerce to more useful types
        self.mp_bits = int(self.mp_bits)
        self.uses_tr1 == bool(self.uses_tr1)
        self.libs = force_to_dict(self.libs)

        self.add = map(lambda f: os.path.join(self.lives_in, f), self.add)

    def __cmp__(self, other):
        if self.basename < other.basename:
            return -1
        if self.basename == other.basename:
            return 0
        return 1

class ArchInfo(object):
    def __init__(self, infofile):
        lex_me_harder(infofile, self,
                      ['aliases', 'submodels', 'submodel_aliases'],
                      { 'realname': '<UNKNOWN>',
                        'default_submodel': None,
                        'endian': None,
                        'unaligned': 'no'
                        })

        self.submodel_aliases = force_to_dict(self.submodel_aliases)

        if self.unaligned == 'ok':
            self.unaligned_ok = 1
        else:
            self.unaligned_ok = 0

    def defines(self, target_submodel):
        macros = ['TARGET_ARCH_IS_%s' % (self.basename.upper())]

        if self.basename != target_submodel:
            macros.append('TARGET_CPU_IS_%s' % (target_submodel.upper()))

        if self.endian != None:
            macros.append('TARGET_CPU_IS_%s_ENDIAN' % (self.endian.upper()))

        macros.append('TARGET_UNALIGNED_LOADSTORE_OK %d' % (self.unaligned_ok))

        return macros

class CompilerInfo(object):
    def __init__(self, infofile):
        lex_me_harder(infofile, self,
                      ['so_link_flags', 'mach_opt', 'mach_abi_linking'],
                      { 'realname': '<UNKNOWN>',
                        'binary_name': None,
                        'compile_option': '-c ',
                        'output_to_option': '-o ',
                        'add_include_dir_option': '-I',
                        'add_lib_dir_option': '-L',
                        'add_lib_option': '-l',
                        'lib_opt_flags': '',
                        'check_opt_flags': '',
                        'debug_flags': '',
                        'no_debug_flags': '',
                        'shared_flags': '',
                        'lang_flags': '',
                        'warning_flags': '',
                        'dll_import_flags': '',
                        'dll_export_flags': '',
                        'ar_command': None,
                        'makefile_style': '',
                        'compiler_has_tr1': False,
                        })

        self.so_link_flags = force_to_dict(self.so_link_flags)
        self.mach_abi_linking = force_to_dict(self.mach_abi_linking)

        self.mach_opt_flags = {}

        while self.mach_opt != []:
            proc = self.mach_opt.pop(0)
            if self.mach_opt.pop(0) != '->':
                raise Exception("Parsing err in %s mach_opt" % (self.basename))

            flags = self.mach_opt.pop(0)
            regex = ''

            if len(self.mach_opt) > 0 and \
               (len(self.mach_opt) == 1 or self.mach_opt[1] != '->'):
                regex = self.mach_opt.pop(0)

            self.mach_opt_flags[proc] = (flags,regex)

        del self.mach_opt

    def mach_opts(self, arch, submodel):

        def submodel_fixup(tup):
            return tup[0].replace('SUBMODEL', submodel.replace(tup[1], ''))

        if submodel in self.mach_opt_flags:
            return submodel_fixup(self.mach_opt_flags[submodel])
        if arch in self.mach_opt_flags:
            return submodel_fixup(self.mach_opt_flags[arch])

        return ''

    def so_link_command_for(self, osname):
        if osname in self.so_link_flags:
            return self.so_link_flags[osname]
        return self.so_link_flags['default']

    def defines(self):
        if self.compiler_has_tr1:
            return ['USE_STD_TR1']
        return []

class OsInfo(object):
    def __init__(self, infofile):
        lex_me_harder(infofile, self,
                      ['aliases', 'target_features', 'supports_shared'],
                      { 'realname': '<UNKNOWN>',
                        'os_type': None,
                        'obj_suffix': 'o',
                        'so_suffix': 'so',
                        'static_suffix': 'a',
                        'ar_command': 'ar crs',
                        'ar_needs_ranlib': False,
                        'install_root': '/usr/local',
                        'header_dir': 'include',
                        'lib_dir': 'lib',
                        'doc_dir': 'share/doc',
                        'install_cmd_data': 'install -m 644',
                        'install_cmd_exec': 'install -m 755'
                        })

        self.ar_needs_ranlib = bool(self.ar_needs_ranlib)

    def ranlib_command(self):
        if self.ar_needs_ranlib == True:
            return 'ranlib'
        else:
            return 'true' # no-op

    def defines(self):
        return ['TARGET_OS_IS_%s' % (self.basename.upper())] + \
               ['TARGET_OS_HAS_' + feat.upper()
                for feat in self.target_features]

def canon_processor(archinfo, proc):
    for ainfo in archinfo.values():
        if ainfo.basename == proc or proc in ainfo.aliases:
            return (ainfo.basename, ainfo.basename)
        else:
            for sm_alias in ainfo.submodel_aliases:
                if re.match(sm_alias, proc) != None:
                    return (ainfo.basename,ainfo.submodel_aliases[sm_alias])
            for submodel in ainfo.submodels:
                if re.match(submodel, proc) != None:
                    return (ainfo.basename,submodel)

    raise Exception("Unknown or unidentifiable processor '%s'" % (proc))

def guess_processor(archinfo):
    base_proc = platform.machine()
    full_proc = platform.processor()

    full_proc = full_proc.replace(' ', '').lower()

    for junk in ['(tm)', '(r)']:
        full_proc = full_proc.replace(junk, '')

    for ainfo in archinfo.values():
        if ainfo.basename == base_proc or base_proc in ainfo.aliases:
            base_proc = ainfo.basename

            for sm_alias in ainfo.submodel_aliases:
                if re.match(sm_alias, full_proc) != None:
                    return (base_proc,ainfo.submodel_aliases[sm_alias])
            for submodel in ainfo.submodels:
                if re.match(submodel, full_proc) != None:
                    return (base_proc,submodel)

    # No matches, so just use the base proc type
    return (base_proc,base_proc)

"""
Read a whole file into memory as a string
"""
def slurp_file(filename):
    if filename is None:
        return ''
    return ''.join(open(filename).readlines())

"""
Perform template substitution
"""
def process_template(template_file, variables):
    class PercentSignTemplate(Template):
        delimiter = '%'

    try:
        template = PercentSignTemplate(slurp_file(template_file))
        return template.substitute(variables)
    except KeyError, e:
        raise Exception('Unbound var %s in template %s' % (e, template_file))

"""
Create the template variables needed to process the makefile, build.h, etc
"""
def create_template_vars(build_config, options, modules, cc, arch, osinfo):
    def make_cpp_macros(macros):
        return '\n'.join(['#define BOTAN_' + macro for macro in macros])

    """
    Figure out what external libraries are needed based on selected modules
    """
    def link_to():
        libs = set()
        for module in modules:
            for (osname,link_to) in module.libs.iteritems():
                if osname == 'all' or osname == osinfo.basename:
                    libs.add(link_to)
                else:
                    match = re.match('^all!(.*)', osname)
                    if match is not None:
                        exceptions = match.group(1).split(',')
                        if osinfo.basename not in exceptions:
                            libs.add(link_to)
        return sorted(libs)

    def objectfile_list(sources, obj_dir):
        for src in sources:
            basename = os.path.basename(src)

            for src_suffix in ['.cpp', '.S']:
                basename = basename.replace(src_suffix,
                                            '.' + osinfo.obj_suffix)

            yield os.path.join(obj_dir, basename)

    """
    Form snippets of makefile for building each source file
    """
    def build_commands(sources, obj_dir, flags):
        for (obj_file,src) in zip(objectfile_list(sources, obj_dir), sources):
            yield "%s: %s\n\t$(CXX) %s%s $(%s_FLAGS) %s$? %s$@\n" % (
                obj_file, src,
                cc.add_include_dir_option,
                build_config.include_dir,
                flags,
                cc.compile_option,
                cc.output_to_option)

    def makefile_list(items):
        return (' '*16).join([item + ' \\\n' for item in items])

    vars = {
        'version_major': build_config.version_major(),
        'version_minor': build_config.version_minor(),
        'version_patch': build_config.version_patch(),
        'version':       build_config.version_string(),
        'so_version': build_config.soversion_string(),

        'timestamp': build_config.timestamp(),
        'user':      build_config.username(),
        'hostname':  build_config.hostname(),
        'command_line': ' '.join(sys.argv),
        'local_config': slurp_file(options.local_config),

        'prefix': options.prefix or osinfo.install_root,
        'libdir': options.libdir or osinfo.lib_dir,
        'includedir': options.includedir or osinfo.header_dir,
        'docdir': options.docdir or osinfo.doc_dir,

        'doc_src_dir': 'doc',
        'build_dir': options.build_dir,

        'os': options.os,
        'arch': options.arch,
        'submodel': options.cpu,

        'cc': cc.binary_name,
        'lib_opt': cc.lib_opt_flags,
        'mach_opt': cc.mach_opts(options.arch, options.cpu),
        'check_opt': cc.check_opt_flags,
        'lang_flags': cc.lang_flags,
        'warn_flags': cc.warning_flags,
        'shared_flags': cc.shared_flags,
        'dll_export_flags': cc.dll_export_flags,

        'so_link': cc.so_link_command_for(osinfo.basename),

        'link_to': ' '.join([cc.add_lib_option + lib for lib in link_to()]),

        'module_defines': make_cpp_macros(['HAS_' + m.define
                                           for m in modules if m.define]),

        'target_os_defines': make_cpp_macros(osinfo.defines()),
        'target_cpu_defines': make_cpp_macros(arch.defines(options.cpu)),
        'target_compiler_defines': make_cpp_macros(cc.defines()),

        'include_files': makefile_list(build_config.headers),

        'lib_objs': makefile_list(
            objectfile_list(build_config.sources,
                            build_config.libobj_dir)),

        'check_objs': makefile_list(
            objectfile_list(build_config.check_sources,
                            build_config.checkobj_dir)),

        'lib_build_cmds': '\n'.join(
            build_commands(build_config.sources,
                           build_config.libobj_dir, 'LIB')),

        'check_build_cmds': '\n'.join(
            build_commands(build_config.check_sources,
                           build_config.checkobj_dir, 'CHECK')),

        'ar_command': cc.ar_command or osinfo.ar_command,
        'ranlib_command': osinfo.ranlib_command(),
        'install_cmd_exec': osinfo.install_cmd_exec,
        'install_cmd_data': osinfo.install_cmd_data,

        'static_suffix': osinfo.static_suffix,
        'so_suffix': osinfo.so_suffix,

        'botan_config': 'botan-config',
        'botan_pkgconfig': 'botan.pc',

        'doc_files': makefile_list(sorted(build_config.doc_files())),

        'mod_list': '\n'.join(['%s (%s)' % (m.basename, m.realname)
                               for m in sorted(modules)]),
        }

    vars['mp_bits'] = 666
    vars['check_prefix'] = 'check prefix'
    vars['lib_prefix'] = 'lib prefix'

    return vars

def choose_modules_to_use(options, modules):
    chosen = []

    for (name,module) in modules.iteritems():

        # First eliminate all modules which simply do not work on target system
        if module.cc != [] and options.compiler not in module.cc:
            continue

        if module.os != [] and options.os not in module.os:
            continue

        if module.arch != [] and options.arch not in module.arch \
               and options.cpu not in module.arch:
            continue

        chosen.append(module)
    return chosen

def setup_build_tree(build_config, options, headers, sources):
    shutil.rmtree(options.build_dir)

    #os.makedirs(include_dir)
    #os.makedirs(checks_dir)
    #os.makedirs(libobj_dir)

    for header_file in headers:
        shutil.copy(header_file, include_dir)

def load_info_files(options):

    def find_files_named(desired_name, in_path):
        for (dirpath, dirnames, filenames) in os.walk(in_path):
            if desired_name in filenames:
                yield os.path.join(dirpath, desired_name)

    modules = dict([(mod.basename, mod) for mod in
                    [ModuleInfo(info) for info in
                     find_files_named('info.txt', 'src')]])

    def list_files_in_build_data(subdir):
        for (dirpath, dirnames, filenames) in \
                os.walk(os.path.join(options.build_data, subdir)):
            for filename in filenames:
                yield os.path.join(dirpath, filename)

    archinfo = dict([(os.path.basename(info), ArchInfo(info))
                     for info in list_files_in_build_data('arch')])

    osinfo   = dict([(os.path.basename(info), OsInfo(info))
                      for info in list_files_in_build_data('os')])

    ccinfo = dict([(os.path.basename(info), CompilerInfo(info))
                    for info in list_files_in_build_data('cc')])

    del osinfo['defaults'] # FIXME

    return (modules, archinfo, ccinfo, osinfo)

def main(argv = None):
    if argv is None:
        argv = sys.argv

    (options, args) = process_command_line(argv[1:])
    if args != []:
        raise Exception('Unhandled option(s) ' + ' '.join(args))

    options.build_data = os.path.join('src', 'build-data')

    (modules, archinfo, ccinfo, osinfo) = load_info_files(options)

    # FIXME: epic fail
    if options.compiler is None:
        options.compiler = 'gcc'

    if options.compiler not in ccinfo:
        raise Exception("Unknown compiler '%s'; available options: %s" % (
            options.compiler, ' '.join(sorted(ccinfo.keys()))))

    if options.os not in osinfo:
        raise Exception("Unknown OS '%s'; available options: %s" % (
            options.os, ' '.join(sorted(osinfo.keys()))))

    if options.cpu is None:
        (options.arch, options.cpu) = guess_processor(archinfo)
    else:
        (options.arch, options.cpu) = canon_processor(archinfo, options.cpu)

    modules_to_use = choose_modules_to_use(options, modules)

    build_config = BuildConfigurationInformation(options, modules_to_use)

    template_vars = create_template_vars(build_config, options,
                                         modules_to_use,
                                         ccinfo[options.compiler],
                                         archinfo[options.arch],
                                         osinfo[options.os])

    #setup_build_tree(build_config, options, headers, sources)

    options.makefile_dir = os.path.join(options.build_data, 'makefile')

    templates_to_proc = {
        os.path.join(options.makefile_dir, 'unix_shr.in'): 'Makefile',
        os.path.join(options.makefile_dir, 'unix.in'): 'Makefile',
        os.path.join(options.makefile_dir, 'nmake.in'): 'Makefile',

        os.path.join(options.build_data, 'buildh.in'): \
           os.path.join(options.build_dir, 'build.h'),

        os.path.join(options.build_data, 'botan-config.in'): \
           os.path.join(options.build_dir, 'botan-config'),

        os.path.join(options.build_data, 'botan.pc.in'): \
           os.path.join(options.build_dir, 'botan-1.8.pc')
        }

    for (template, sink) in templates_to_proc.items():
        process_template(template, template_vars)

if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception, e:
        print >>sys.stderr, e
        #import traceback
        #traceback.print_exc(file=sys.stderr)
