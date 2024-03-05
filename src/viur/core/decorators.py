import abc
import collections
import typing as t

from viur.core.module import Method

__all__ = [
    "access",
    "exposed",
    "force_post",
    "force_ssl",
    "internal_exposed",
    "skey",
]


def exposed(func: t.Callable) -> Method:
    """
    Decorator, which marks a function as exposed.

    Only exposed functions are callable by http-requests.
    Can optionally receive a dict of language->translated name to make that function
    available under different names
    """
    if isinstance(func, dict):
        seo_language_map = func

        # We received said dictionary:
        def expose_with_translations(func: t.Callable) -> Method:
            func = Method.ensure(func)
            func.exposed = True
            func.seo_language_map = seo_language_map
            return func

        return expose_with_translations

    func = Method.ensure(func)
    func.exposed = True
    return func


def internal_exposed(func: t.Callable) -> Method:
    """
    Decorator, which marks a function as internal exposed.
    """
    func = Method.ensure(func)
    func.exposed = False
    return func


def force_ssl(func: t.Callable) -> Method:
    """
    Decorator, which enforces usage of an encrypted channel for a given resource.
    Has no effect on development-servers.
    """
    func = Method.ensure(func)
    func.ssl = True
    return func


def force_post(func: t.Callable) -> Method:
    """
    Decorator, which enforces usage of a http post request.
    """
    func = Method.ensure(func)
    func.methods = ("POST",)
    return func


def access(
    *access: str | list[str] | tuple[str] | set[str] | t.Callable,
    offer_login: bool | str = False,
    message: str | None = None,
) -> t.Callable:
    """
    Decorator, which performs an authentication and authorization check primarily based on the current user's access,
    which is defined via the `UserSkel.access`-bone. Additionally, a callable for individual access checking can be
    provided.

    In case no user is logged in, the decorator enforces to raise an HTTP error 401 - Unauthorized in case no user is
    logged in, otherwise it returns an HTTP error 403 - Forbidden when the specified access parameters prohibit to call
    the decorated method.

    :params access: Access configuration, either names of access rights or a callable for verification.
    :params offer_login: Offers a way to login; Either set it to True, to automatically redirect to /user/login,
        or set it to any other URL.
    :params message: A custom message to be printed when access is denied or unauthorized.

    To check on authenticated users with the access "root" or ("admin" and "file-edit") or "maintainer" use the
    decorator like this:

    .. code-block:: python
        from viur.core.decorators import access
        @access("root", ["admin", "file-edit"], ["maintainer"])
        def my_method(self):
            return "You're allowed!"

    Furthermore, instead of a list/tuple/set/str, a callable can be provided which performs custom access checking,
    and directly is checked on True for access grant.
    """
    access_config = locals()

    def decorator(func):
        meth = Method.ensure(func)
        meth.access = access_config
        return meth

    return decorator


def skey(
    func: t.Callable = None,
    *,
    allow_empty: bool | list[str] | tuple[str] | t.Callable = False,
    forward_payload: str | None = None,
    message: str = None,
    name: str = "skey",
    validate: t.Callable | None = None,
    **extra_kwargs: dict,
) -> Method:
    """
    Decorator, which configures an exposed method for requiring a CSRF-security-key.
    The decorator enforces a raise of HTTP error 406 - Precondition failed in case the security-key is not provided
    or became invalid.

    :param allow_empty: Allows to call the method without a security-key when no other parameters where provided.
        This can also be a tuple or list of keys which are being ignored, or a callable taking args and kwargs, and
        programmatically decide whether security-key is required or not.
    :param forward_payload: Forwards the extracted payload of the security-key to the method under the key specified
        here as a value in kwargs.
    :param message: Allows to specify a custom error message in case a HTTP 406 is raised.
    :param name: Defaults to "skey", but allows also for another name passed to the method.
    :param validate: Allows to specify a Callable used to further evaluate the payload of the security-key.
        Security-keys can be equipped with further data, see the securitykey-module for details.
    :param extra_kwargs: Any provided extra_kwargs are being passed to securitykey.validate as kwargs.
    """
    skey_config = locals()

    def decorator(func):
        meth = Method.ensure(func)
        meth.skey = skey_config
        return meth

    if func is None:
        return decorator

    return decorator(func)


class action_meta(type):

    def __init__(cls, name, bases, attr):
        print(f"call init {(name, bases, attr) = }")
        super().__init__(name, bases, attr)

    def __new__(cls, name, bases, dict_):
        print("Creating class %s%s with attributes %s" % (name, bases, dict_))
        # return type.__new__(cls, name, bases, dict_)
        for attrname, cls_attr in dict_.items():
            mangled_attr = "_{0}__set_name".format(cls_attr.__class__.__name__)
            if hasattr(cls_attr, mangled_attr):
                setattr(cls_attr, 'name', attrname)
        return super().__new__(cls, name, bases, dict_)


class on_action(abc.ABC):
    @property
    @abc.abstractmethod
    def action_name(self) -> str:
        ...

    # def __init__(self, action_name):
    #     print(f"__init__ {action_name = }")
    #     self.action_name = action_name
    #
    def __call__(self, *args, **kwargs):
        print(f"__call__  {self} {args = } {    kwargs = }")
        return self.fn(*args, **kwargs)
        # self.fn = fn

    def __init__(self, fn: t.Callable):
        print(f"__init__ {fn = }")
        self.fn = fn

    def __set_name__(self, owner, name):
        print(f"decorating {self.fn} and using {owner=}")
        self.fn.class_name = owner.__name__

        if not hasattr(owner, "on_handlers"):
            owner.on_handlers: dict[str, list[t.Callable]] = collections.defaultdict(list)
        owner.on_handlers[self.action_name].append(self.fn)

        # then replace ourself with the original method
        # setattr(owner, name, self.fn)

    @classmethod
    def dispatch(cls, caller, *args, **kwargs):
        print(f"dispatch  {cls=} {caller = } with {args=} & {kwargs=}")
        for handler in caller.on_handlers[cls.action_name]:
            print(f"{handler = }")
            handler(caller, *args, **kwargs)

    @classmethod
    def create(cls, action_name: str) -> t.Self:
        return type(f"{action_name}Action", (cls,), {"action_name": action_name})


on_add = on_action.create("add")
on_added = on_action.create("added")
on_edit = on_action.create("edit")
on_edited = on_action.create("edited")
