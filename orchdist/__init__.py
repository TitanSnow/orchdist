from distutils.dist import Distribution
from distutils.cmd import Command
from distutils.ccompiler import new_compiler
from distutils.sysconfig import customize_compiler
from concurrent.futures import ThreadPoolExecutor
import asyncio
from functools import partial
import typing


class SequencifyFail(RuntimeError):
    pass


class OrchDistribution(Distribution):
    def __init__(self, *args, **kwargs):
        self.max_workers = kwargs.get('max_workers')
        if 'max_workers' in kwargs:
            del kwargs['max_workers']
        super().__init__(*args, **kwargs)
        self.is_running = {}

    def sequencify_commands(self, commands):
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
        for subcmd in self.get_command_obj(command).get_sub_commands():
            if not self.have_run.get(subcmd):
                return False
        return True

    def _run_commands(self, commands):
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
                _runs()
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
        self.cmdclass[command] = klass

    def register_cmdclasses(self, cmdclass):
        for command, klass in cmdclass.items():
            self.register_cmdclass(command, klass)

    def add_commands(self, *commands):
        if not hasattr(self, 'commands'):
            self.commands = []
        self.commands.extend(commands)


class OrchCommand(Command):
    cmdclass = {}

    def __init__(self, dist):
        super().__init__(dist)
        OrchDistribution.register_cmdclasses(self.distribution, self.cmdclass)

    @classmethod
    def add_sub_command(cls, command, predicate=None, klass=None):
        cls.sub_commands.append((command, predicate))
        if klass is not None:
            cls.cmdclass[command] = klass

    @classmethod
    def set_command_name(cls, name):
        cls.command_name = name

    @classmethod
    def create_subclass(cls):
        class UnnamedCommand(cls):
            cmdclass = {}
            sub_commands = []
            command_name = 'UnnamedCommand'
        return UnnamedCommand

    @classmethod
    def on(cls, name=None, fn=None):
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
    def __init__(self, distribution=None):
        self.cmddep = {}
        self.cmdcls = {}
        self.cmdfn = {}
        self.distribution = distribution

    def add(self, command, deps=tuple()):
        self.cmddep[command] = deps

    def on(self, command, name=None, fn=None):
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
