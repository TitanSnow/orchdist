"""
A python module for executing ``distutils`` commands in concurrency
"""


#   Copyright (C) 2017 TitanSnow

#   This library is free software; you can redistribute it and/or
#   modify it under the terms of the GNU Lesser General Public
#   License as published by the Free Software Foundation; either
#   version 2.1 of the License, or (at your option) any later version.

#   This library is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#   Lesser General Public License for more details.

#   You should have received a copy of the GNU Lesser General Public
#   License along with this library; if not, write to the Free Software
#   Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301
#   USA


#   Copyright (c) 2013 [Richardson & Sons, LLC](http://richardsonandsons.com/)

#   Permission is hereby granted, free of charge, to any person obtaining
#   a copy of this software and associated documentation files (the
#   "Software"), to deal in the Software without restriction, including
#   without limitation the rights to use, copy, modify, merge, publish,
#   distribute, sublicense, and/or sell copies of the Software, and to
#   permit persons to whom the Software is furnished to do so, subject to
#   the following conditions:

#   The above copyright notice and this permission notice shall be
#   included in all copies or substantial portions of the Software.

#   THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
#   EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
#   MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
#   NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
#   LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
#   OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
#   WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.


from distutils.dist import Distribution
from distutils.cmd import Command
from distutils.ccompiler import new_compiler
from distutils.sysconfig import customize_compiler
from concurrent.futures import ThreadPoolExecutor
import asyncio
from functools import partial
import typing


class SequencifyFail(RuntimeError):
    """internal exception -- fail to sequencify"""
    pass


class OrchDistribution(Distribution):
    """the core of orchdist

    concurrent distclass

    pass to ``distclass`` keyword when calling ``setup()`` to use in ``setup.py``

    *OrchDistribution expects commands it runs to run their sub commands in ``run`` method*"""

    def __init__(self, *args, **kwargs):
        """
        keyword arguments:
          max_workers: specify the max number of workers to execute commands
        """
        self.max_workers = kwargs.get('max_workers')
        if 'max_workers' in kwargs:
            del kwargs['max_workers']
        super().__init__(*args, **kwargs)
        self.is_running = {}

    def sequencify_commands(self, commands):
        """sequencify ``commands``. returns a list of sequencified commands

        sub commands will be put before their parent classes

        raise ``SequencifyFail`` if fails"""

        def sequencify(commands, results, nest):
            for command in commands:
                if command not in results:
                    if command in nest:
                        raise SequencifyFail('recursive')
                    deps = self.get_command_obj(command).get_sub_commands()
                    if deps:
                        nest.append(command)
                        sequencify(deps, results, nest)
                        nest.pop()
                    results.append(command)
            return results
        return sequencify(commands, [], [])

    def is_sub_commands_have_run(self, command):
        """returns whether all sub commands of ``command`` have run"""
        for subcmd in self.get_command_obj(command).get_sub_commands():
            if not self.have_run.get(subcmd):
                return False
        return True

    def _run_commands(self, commands):
        """run given ``commands`` in concurrency"""
        try:
            commands = self.sequencify_commands(commands)
        except SequencifyFail:
            for cmd in commands:
                super(OrchDistribution, self).run_command(cmd)
            return
        with ThreadPoolExecutor(max_workers=self.max_workers) as job_pool:
            event_loop = asyncio.new_event_loop()
            try:
                futures = []
                def _runs():
                    def _run(command):
                        try:
                            super(OrchDistribution, self).run_command(command)
                        except Exception as e:
                            event_loop.stop()
                            return e
                        finally:
                            del self.is_running[command]
                        event_loop.call_soon_threadsafe(_runs)
                        return None
                    finished = True
                    for cmd in commands:
                        if not self.have_run.get(cmd):
                            finished = False
                            break
                    if finished:
                        event_loop.stop()
                        return
                    for cmd in commands:
                        if not self.have_run.get(cmd) and not self.is_running.get(cmd) and self.is_sub_commands_have_run(cmd):
                            self.is_running[cmd] = True
                            futures.append(job_pool.submit(_run, cmd))
                event_loop.call_soon(_runs)
                event_loop.run_forever()
                for future in futures:
                    e = future.result()
                    if e is not None:
                        raise e
            finally:
                event_loop.close()

    def run_command(self, command):
        self._run_commands([command])

    def run_commands(self):
        self._run_commands(self.commands)

    def register_cmdclass(self, command, klass):
        """register ``klass`` with name ``command`` in ``self.cmdclass``"""
        self.cmdclass[command] = klass

    def register_cmdclasses(self, cmdclass):
        """register ``cmdclass`` to ``self.cmdclass``"""
        for command, klass in cmdclass.items():
            self.register_cmdclass(command, klass)

    def add_commands(self, *commands):
        """add ``commands`` to ``self.commands``"""
        if not hasattr(self, 'commands'):
            self.commands = []
        self.commands.extend(commands)


class OrchCommand(Command):
    """base class of commands in orchdist

    added useful methods to custom a command"""

    cmdclass = {}

    def __init__(self, dist):
        super().__init__(dist)
        OrchDistribution.register_cmdclasses(self.distribution, self.cmdclass)

    @classmethod
    def add_sub_command(cls, command, predicate=None, klass=None):
        """add sub command with name ``command``

        this sub command will be run if ``predicate`` is None or call it returns True

        the command class of this sub command is set to ``klass``"""

        cls.sub_commands.append((command, predicate))
        if klass is not None:
            cls.cmdclass[command] = klass

    @classmethod
    def set_command_name(cls, name):
        """set name of command class"""
        cls.command_name = name

    @classmethod
    def create_subclass(cls):
        """create a subclass of this class"""
        class UnnamedCommand(cls):
            cmdclass = {}
            sub_commands = []
            command_name = 'UnnamedCommand'
        return UnnamedCommand

    @classmethod
    def on(cls, name=None, fn=None):
        """redefine method ``name`` with ``fn`` of this class

        ``name`` will be ``fn.__name__`` if ``name`` is None

        if ``fn`` is None, will return a function to be used as a decorator like ::

            @cmdclass.on()
            def run(self):
                pass

        """

        if fn is not None:
            setattr(cls, name if name is not None else fn.__name__, fn)
        else:
            def func(fn):
                cls.on(name, fn)
                return fn
            return func

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        for cmd_name in self.get_sub_commands():
            self.run_command(cmd_name)


class CommandCreator:
    """a util class to create commands"""
    def __init__(self, distribution=None):
        self.cmddep = {}
        self.cmdcls = {}
        self.cmdfn = {}
        self.distribution = distribution

    def add(self, command, deps=tuple()):
        """add command with name ``command`` and dependencies ``deps``"""
        self.cmddep[command] = deps

    def on(self, command, name=None, fn=None):
        """redefine method ``name`` of ``command``

        ``name`` will be ``fn.__name__`` if ``name`` is None

        if ``fn`` is None, will return a function to be used as a decorator like ::

            @creator.on('command1')
            def run(self):
                pass

        """
        if fn is not None:
            if command not in self.cmdfn:
                self.cmdfn[command] = {}
            self.cmdfn[command][name if name is not None else fn.__name__] = fn
        else:
            def func(fn):
                self.on(command, name, fn)
                return fn
            return func

    def create(self, command, klass=OrchCommand):
        """create command class of ``command`` to be subclass of ``klass``"""
        if command in self.cmdcls:
            return self.cmdcls[command]
        cmdclass = klass.create_subclass()
        cmdclass.set_command_name(command)
        for name, fn in self.cmdfn.get(command, {}).items():
            cmdclass.on(name, fn)
        self.cmdcls[command] = cmdclass
        for dep in self.cmddep[command]:
            cmdclass.add_sub_command(dep, None, self.create(dep, klass))
        return cmdclass

    def create_all(self):
        """create all command classes. returns a dict maps command name to command class"""
        result = {}
        for cmd in self.cmddep:
            result[cmd] = self.create(cmd)
        return result

    def apply(self, dist=None):
        if dist is None:
            dist = self.distribution
        dist.register_cmdclasses(self.create_all())
        dist.add_commands(*self.create_all().keys())


class BuildC(OrchCommand):
    plat = None
    compiler = None
    verbose = 0
    dry_run = 0
    force = 0

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.result = None

    def new_compiler(self):
        compiler = new_compiler(self.get_option('plat'),
                                self.get_option('compiler'),
                                self.get_option('verbose'),
                                self.get_option('dry_run'),
                                self.get_option('force'))
        customize_compiler(compiler)
        return compiler

    def get_option(self, option):
        value = getattr(self, option)
        if isinstance(value, typing.Callable):
            setattr(self, option, value())
            return getattr(self, option)
        else:
            return value


class Preprocess(BuildC):
    source = None
    output_file = None
    macros = None
    include_dirs = None
    extra_preargs = None
    extra_postargs = None

    def run(self):
        super().run()
        compiler = self.new_compiler()
        self.result = compiler.preprocess(self.get_option('source'),
                                          self.get_option('output_file'),
                                          self.get_option('macros'),
                                          self.get_option('include_dirs'),
                                          self.get_option('extra_preargs'),
                                          self.get_option('extra_postargs'))


class Compile(BuildC):
    sources = None
    output_dir = None
    macros = None
    include_dirs = None
    debug = 0
    extra_preargs = None
    extra_postargs = None
    depends = None

    def run(self):
        super().run()
        compiler = self.new_compiler()
        self.result = compiler.compile(self.get_option('sources'),
                                       self.get_option('output_dir'),
                                       self.get_option('macros'),
                                       self.get_option('include_dirs'),
                                       self.get_option('debug'),
                                       self.get_option('extra_preargs'),
                                       self.get_option('extra_postargs'),
                                       self.get_option('depends'))


class StaticLink(BuildC):
    objects = None
    output_libname = None
    output_dir = None
    debug = 0
    target_lang = None

    def run(self):
        super().run()
        compiler = self.new_compiler()
        self.result = compiler.create_static_lib(self.get_option('objects'),
                                                 self.get_option('output_libname'),
                                                 self.get_option('output_dir'),
                                                 self.get_option('debug'),
                                                 self.get_option('target_lang'))


class Link(BuildC):
    SHARED_OBJECT = "shared_object"
    SHARED_LIBRARY = "shared_library"
    EXECUTABLE = "executable"
    target_desc = None
    objects = None
    output_filename = None
    output_dir = None
    libraries = None
    library_dirs = None
    runtime_library_dirs = None
    export_symbols = None
    debug = 0
    extra_preargs = None
    extra_postargs = None
    build_temp = None
    target_lang = None

    def run(self):
        super().run()
        compiler = self.new_compiler()
        self.result = compiler.link(self.get_option('target_desc'),
                                    self.get_option('objects'),
                                    self.get_option('output_filename'),
                                    self.get_option('output_dir'),
                                    self.get_option('libraries'),
                                    self.get_option('library_dirs'),
                                    self.get_option('runtime_library_dirs'),
                                    self.get_option('export_symbols'),
                                    self.get_option('debug'),
                                    self.get_option('extra_preargs'),
                                    self.get_option('extra_postargs'),
                                    self.get_option('build_temp'),
                                    self.get_option('target_lang'))


class TargetCreator:
    def __init__(self, result):
        self.result = result

    def do(self, cmdclass):
        self.result['_cmdclass'] = cmdclass.create_subclass()
        return self

    def set_option(self, option, value):
        self.result[option] = value
        return self

    def __getattr__(self, attr):
        actions = {
            'preprocess': partial(self.do, Preprocess),
            'compile': partial(self.do, Compile),
            'static_link': partial(self.do, StaticLink),
            'link': partial(self.do, Link),
        }
        return actions.get(attr, partial(self.set_option, attr))

    @staticmethod
    def archive(target):
        target = target.copy()
        klass = target['_cmdclass']
        del target['_cmdclass']
        for k, v in target.items():
            getattr(klass, k)
            setattr(klass, k, v)
        return klass


class Builder(CommandCreator):
    def __init__(self, distribution=None):
        super().__init__(distribution)
        self.targets = {}

    def target(self, name, deps=tuple()):
        self.add(name, deps)
        self.targets[name] = {}
        return TargetCreator(self.targets[name])

    def create(self, command, klass=OrchCommand):
        if command not in self.targets:
            return super().create(command, klass)
        else:
            return super().create(command, TargetCreator.archive(self.targets[command]))

    def result_of(self, command):
        return lambda self: self.distribution.get_command_obj(command).result


__all__ = ('OrchDistribution',
           'OrchCommand',
           'CommandCreator',
           'BuildC',
           'Preprocess',
           'Compile',
           'StaticLink',
           'Link',
           'TargetCreator',
           'Builder')
__version__ = '0.1.0.dev1'
