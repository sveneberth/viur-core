import base64
import datetime
import json
import numbers
import typing as t
from pprint import pprint

import pytz

from viur.core import db


class ViURJsonEncoder(json.JSONEncoder):
    """
    Adds support for db.Key, db.Entity, datetime, bytes and and converts the provided obj
    into a special dict with JSON-serializable values.
    """

    def default(self, obj: t.Any) -> t.Any:
        print(f"{obj.__class__.__name__}: {obj}")
        if isinstance(obj, bytes):
            return {".__bytes__": base64.b64encode(obj).decode("ASCII")}
        elif isinstance(obj, datetime.datetime):
            return {".__datetime__": obj.astimezone(pytz.UTC).isoformat()}
        elif isinstance(obj, datetime.timedelta):
            return {".__timedelta__": obj / datetime.timedelta(microseconds=1)}
        elif isinstance(obj, set):
            return {".__set__": list(obj)}
        elif hasattr(obj, "__iter__"):
            print(f"iter {obj=}")
            return tuple(obj)
        # cannot be tested in tests...
        elif isinstance(obj, db.Key):
            return {".__key__": db.encodeKey(obj)}
        elif isinstance(obj, db.Entity):
            # TODO: Handle SkeletonInstance as well?
            return {
                ".__entity__": dict(obj),
                ".__key__": db.encodeKey(obj.key) if obj.key else None
            }

        return super().default(obj)

    def iterencode(self, o, _one_shot=False):
        print(f"iterencode :: {o.__class__.__name__}: {o} {_one_shot=}")
        return super().iterencode(o, _one_shot)


def rewrite_entity(o):
    if isinstance(o, (str, bytes, numbers.Number, type(None))):
        return o
    elif isinstance(o, set):
        return set(rewrite_entity(x) for x in o)
    elif isinstance(o, db.Entity):
        return {
            ".__entity__": rewrite_entity(dict(o)),
            ".__key__": db.encodeKey(o.key) if o.key else None
        }
    elif isinstance(o, dict):
        return {rewrite_entity(k): rewrite_entity(v) for k, v in o.items()}
    elif hasattr(o, "__iter__"):
        return tuple(rewrite_entity(x) for x in o)
    print(f"MIssing case for <{type(o)}>{o=}")
    return o


def dumps(obj: t.Any, *, cls=ViURJsonEncoder, **kwargs) -> str:
    """
    Wrapper for json.dumps() which converts additional ViUR datatypes.
    """
    print(f"IN >>>")
    pprint(obj)
    print(f"OUT >>>")
    pprint(rewrite_entity(obj))
    return json.dumps(rewrite_entity(obj), cls=cls, **kwargs)


def _decode_object_hook(obj: t.Any):
    """
        Inverse for _preprocess_json_object, which is an object-hook for json.loads.
        Check if the object matches a custom ViUR type and recreate it accordingly.
    """
    if len(obj) == 1:
        if buf := obj.get(".__bytes__"):
            return base64.b64decode(buf)
        elif date := obj.get(".__datetime__"):
            return datetime.datetime.fromisoformat(date)
        elif microseconds := obj.get(".__timedelta__"):
            return datetime.timedelta(microseconds=microseconds)
        elif key := obj.get(".__key__"):
            return db.Key.from_legacy_urlsafe(key)
        elif items := obj.get(".__set__"):
            return set(items)

    elif len(obj) == 2 and all(k in obj for k in (".__entity__", ".__key__")):
        # TODO: Handle SkeletonInstance as well?
        entity = db.Entity(db.Key.from_legacy_urlsafe(obj[".__key__"]) if obj[".__key__"] else None)
        entity.update(obj[".__entity__"])
        return entity

    return obj


def loads(s: str, *, object_hook=_decode_object_hook, **kwargs) -> t.Any:
    """
    Wrapper for json.loads() which recreates additional ViUR datatypes.
    """
    return json.loads(s, object_hook=object_hook, **kwargs)
