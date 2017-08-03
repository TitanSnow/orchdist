from distutils.dist import Distribution
from distutils.cmd import Command
from concurrent.futures import ThreadPoolExecutor
import asyncio


class SequencifyFail(RuntimeError):
    pass


class OrchDistribution(Distribution):
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
        with ThreadPoolExecutor() as job_pool:
            event_loop = asyncio.new_event_loop()
            futures = []
            def _runs():
                def _run(command):
                    try:
                        super(OrchDistribution, self).run_command(command)
                    except Exception as e:
                        event_loop.stop()
                        return e
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
                    if not self.have_run.get(cmd) and self.is_sub_commands_have_run(cmd):
                        futures.append(job_pool.submit(_run, cmd))
            _runs()
            event_loop.run_forever()
            for future in futures:
                e = future.result()
                if e is not None:
                    raise e

    def run_command(self, command):
        self._run_commands([command])

    def run_commands(self):
        self._run_commands(self.commands)


__all__ = ('OrchDistribution',)
