from distutils.dist import Distribution
from distutils.cmd import Command
from distutils.ccompiler import new_compiler
from distutils.sysconfig import customize_compiler
from concurrent.futures import ThreadPoolExecutor
import asyncio


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
    def __init__(self):
        self.cmddep = {}
        self.cmdcls = {}
        self.cmdfn = {}

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
        compiler = new_compiler(self.plat,
                                self.compiler,
                                self.verbose,
                                self.dry_run,
                                self.force)
        customize_compiler(compiler)
        return compiler


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
        self.result = compiler.preprocess(self.source,
                                          self.output_file,
                                          self.macros,
                                          self.include_dirs,
                                          self.extra_preargs,
                                          self.extra_postargs)


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
        self.result = compiler.compile(self.sources,
                                       self.output_dir,
                                       self.macros,
                                       self.include_dirs,
                                       self.debug,
                                       self.extra_preargs,
                                       self.extra_postargs,
                                       self.depends)


class StaticLink(BuildC):
    objects = None
    output_libname = None
    output_dir = None
    debug = 0
    target_lang = None

    def run(self):
        super().run()
        compiler = self.new_compiler()
        self.result = compiler.create_static_lib(self.objects,
                                                 self.output_libname,
                                                 self.output_dir,
                                                 self.debug,
                                                 self.target_lang)


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
        self.result = compiler.link(self.target_desc,
                                    self.objects,
                                    self.output_filename,
                                    self.output_dir,
                                    self.libraries,
                                    self.library_dirs,
                                    self.runtime_library_dirs,
                                    self.export_symbols,
                                    self.debug,
                                    self.extra_preargs,
                                    self.extra_postargs,
                                    self.build_temp,
                                    self.target_lang)


__all__ = ('OrchDistribution',
           'OrchCommand',
           'CommandCreator',
           'BuildC',
           'Preprocess',
           'Compile',
           'StaticLink',
           'Link')
