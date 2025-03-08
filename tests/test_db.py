import types
import unittest

class TestDb(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from main import monkey_patch
        monkey_patch()

    def test_put(self):
        from viur.core import db

        entity = db.Entity(db.Key("foo", "bar"))
        entity["baz"] = 123
        db.Put(entity)

        query = db.Query("foo").run(100)
        print(query)

    def tearDown(self):
        from viur.core.config import conf
        conf.strict_mode = False
