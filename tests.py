import unittest
import time
import orchdist


class TestOrchdist(unittest.TestCase):
    @staticmethod
    def _seq_test(self, src, dest, long_test=False):
        crt = orchdist.CommandCreator()
        result = []
        crt.add('a')
        crt.add('b', ['a'])
        crt.add('c', ['a'])
        crt.add('d', ['b', 'c'])
        crt.add('e', ['f'])
        crt.add('f', ['e'])
        crt.add('g', ['g'])

        @crt.on('a')
        @crt.on('b')
        @crt.on('c')
        @crt.on('d')
        def run(self):
            if long_test:
                time.sleep(0.05)
            result.append(self.get_command_name())

        dist = orchdist.OrchDistribution()
        dist.register_cmdclasses(crt.create_all())
        dist.add_commands(*list(src))

        try:
            actual = dist.sequencify_commands(list(src))
        except orchdist.SequencifyFail:
            self.assertEqual(dest, None)
            return
        self.assertEqual(list(dest), actual)

        if len(src) == 1:
            dist.run_command(src)
        else:
            dist.run_commands()
        self.assertEqual(len(result), len(dest))
        self.assertEqual(set(result), set(dest))
        vis = set()
        for cmd in result:
            for dep in dist.get_command_obj(cmd).get_sub_commands():
                self.assertIn(dep, vis)
            vis.add(cmd)
            self.assertFalse(bool(dist.is_running.get(cmd)))
            self.assertTrue(bool(dist.have_run.get(cmd)))

    @staticmethod
    def seq_test(self, src, dest):
        TestOrchdist._seq_test(self, src, dest, False)
        TestOrchdist._seq_test(self, src, dest, True)

    def test_a2a(self):
        TestOrchdist.seq_test(self, 'a', 'a')

    def test_aa2a(self):
        TestOrchdist.seq_test(self, 'aa', 'a')

    def test_c2ac(self):
        TestOrchdist.seq_test(self, 'c', 'ac')

    def test_b2ab(self):
        TestOrchdist.seq_test(self, 'b', 'ab')

    def test_cb2acb(self):
        TestOrchdist.seq_test(self, 'cb', 'acb')

    def test_bc2abc(self):
        TestOrchdist.seq_test(self, 'bc', 'abc')

    def test_ba2ab(self):
        TestOrchdist.seq_test(self, 'ba', 'ab')

    def test_d2abcd(self):
        TestOrchdist.seq_test(self, 'd', 'abcd')

    def test_cd2acbd(self):
        TestOrchdist.seq_test(self, 'cd', 'acbd')

    def test_bd2abcd(self):
        TestOrchdist.seq_test(self, 'bd', 'abcd')

    def test_e2recursive(self):
        TestOrchdist.seq_test(self, 'e', None)

    def test_g2recursive(self):
        TestOrchdist.seq_test(self, 'g', None)

    def test_raise(self):
        crt = orchdist.CommandCreator()
        crt.add('good')
        crt.add('bad')
        class BadGuy(Exception):
            pass
        @crt.on('bad')
        def run(self):
            raise BadGuy
        dist = orchdist.OrchDistribution()
        dist.register_cmdclasses(crt.create_all())
        dist.add_commands(*crt.create_all().keys())
        with self.assertRaises(BadGuy):
            dist.run_commands()
        self.assertFalse(bool(dist.is_running.get('bad')))
        self.assertFalse(bool(dist.have_run.get('bad')))

    def test_OrchCommand_on(self):
        dist = orchdist.Distribution()
        cmd = orchdist.OrchCommand(dist)
        run = False
        cmd.run()
        self.assertFalse(run)
        @cmd.on('run')
        def another(self):
            nonlocal run
            run = True
        cmd.run()
        self.assertTrue(run)

    def test_run_command_fallback(self):
        crt = orchdist.CommandCreator()
        crt.add('a', ['b'])
        crt.add('b', ['a'])
        result = []
        @crt.on('a')
        @crt.on('b')
        def run(self):
            result.append(self.get_command_name())
        dist = orchdist.OrchDistribution()
        dist.register_cmdclasses(crt.create_all())
        dist.add_commands(*crt.create_all().keys())
        dist.run_commands()
        self.assertEqual(len(result), 2)
        self.assertEqual(set(result), set('ab'))
        self.assertTrue(bool(dist.have_run.get('a')))
        self.assertTrue(bool(dist.have_run.get('b')))
        self.assertFalse(bool(dist.is_running.get('a')))
        self.assertFalse(bool(dist.is_running.get('b')))

    def test_max_workers(self):
        # single worker
        dist = orchdist.OrchDistribution(max_workers=1)
        crt = orchdist.CommandCreator()
        result = []
        crt.add('a', ['b', 'c'])
        crt.add('b')
        crt.add('c')
        @crt.on('a')
        @crt.on('b')
        @crt.on('c')
        def run(self):
            name = self.get_command_name()
            if name == 'b':
                time.sleep(0.05)
            result.append(name)
        dist.register_cmdclasses(crt.create_all())
        dist.add_commands('a')
        dist.run_command('a')
        self.assertEqual(result, ['b', 'c', 'a'])
        dist = orchdist.OrchDistribution(max_workers=2)
        dist.register_cmdclasses(crt.create_all())
        dist.add_commands('a')
        result = []
        dist.run_command('a')
        self.assertEqual(result, ['c', 'b', 'a'])


def suite():
    return unittest.TestLoader().loadTestsFromTestCase(TestOrchdist)


if __name__ == '__main__':
    unittest.main(verbosity=2)
