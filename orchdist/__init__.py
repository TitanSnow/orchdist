from distutils.dist import Distribution
from distutils.cmd import Command
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
        pass


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


__all__ = ('OrchDistribution', 'OrchCommand', 'CommandCreator')
