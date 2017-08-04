import unittest
import orchdist


class TestOrchdist(unittest.TestCase):
    @staticmethod
    def seq_test(self, src, dest):
        crt = orchdist.CommandCreator()
        result = []
        def run(self):
            result.append(self.get_command_name())
        crt.add('a')
        crt.on('a', fn=run)
        crt.add('b', ['a'])
        crt.on('b', fn=run)
        crt.add('c', ['a'])
        crt.on('c', fn=run)
        crt.add('d', ['b', 'c'])
        crt.on('d', fn=run)
        crt.add('e', ['f'])
        crt.add('f', ['e'])
        crt.add('g', ['g'])

        dist = orchdist.OrchDistribution()
        dist.register_cmdclasses(crt.create_all())
        dist.add_commands(*crt.create_all().keys())

        try:
            actual = dist.sequencify_commands(list(src))
        except orchdist.SequencifyFail:
            self.assertEqual(dest, None)
            return
        self.assertEqual(list(dest), actual)

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


if __name__ == '__main__':
    unittest.main(verbosity=2)
