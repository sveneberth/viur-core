from abstract import ViURTestCase


class TestDb(ViURTestCase):
    def test_put(self):
        from viur.core import db

        entity = db.Entity(db.Key("foo", "bar"))
        entity["baz"] = 123
        print(entity.key)
        print(f"{entity.key=}")
        print(f"{entity.key.project=}")
        db.Put(entity)

        query = db.Query("foo").run(100)
        print(query)

    def tearDown(self):
        from viur.core.config import conf
        conf.strict_mode = False
