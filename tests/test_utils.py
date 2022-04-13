import unittest


class TestUtils(unittest.TestCase):

	def test_escapeString(self):
		from viur.core.utils import escapeString

		self.assertEqual("None", escapeString(None))
		self.assertEqual("abcde", escapeString("abcdefghi", maxLength=5))
		self.assertEqual("&lt;html&gt;&&lt;/html&gt;", escapeString("<html>\n&\0</html>"))
