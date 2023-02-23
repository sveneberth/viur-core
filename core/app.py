import logging  # this import has to stay here, see #571
from types import ModuleType
from typing import Callable, Dict, Union

import webob

# noinspection PyUnresolvedReferences
from viur.core import i18n, logging as viurLogging, request, \
    session, utils  # unused import, must exist, initializes request logging
from viur.core.config import conf
from viur.core.router import Router
from viur.core.tasks import runStartupTasks


class App:
    def __init__(self, modules: Union[object, ModuleType], render: Union[ModuleType, Dict] = None,
                 default: str = "html"):
        super().__init__()

        from viur.core.bones.base import setSystemInitialized
        # noinspection PyUnresolvedReferences
        import skeletons  # This import is not used here but _must_ remain to ensure that the
        # application's data models are explicitly imported at some place!
        if conf["viur.instance.project_id"] not in conf["viur.validApplicationIDs"]:
            raise RuntimeError(
                f"""Refusing to start, {conf["viur.instance.project_id"]=} is not in {conf["viur.validApplicationIDs"]=}""")
        if not render:
            import viur.core.render
            render = viur.core.render
        # conf["viur.mainApp"] = buildApp(modules, render, default)
        self.router = Router(modules, render, default)
        conf["viur.mainApp"] = self
        # conf["viur.wsgiApp"] = webapp.WSGIApplication([(r'/(.*)', BrowseHandler)])
        # Ensure that our Content Security Policy Header Cache gets build
        from viur.core import securityheaders
        securityheaders._rebuildCspHeaderCache()
        securityheaders._rebuildPermissionHeaderCache()
        setSystemInitialized()
        # Assert that all security related headers are in a sane state
        if conf["viur.security.contentSecurityPolicy"] and conf["viur.security.contentSecurityPolicy"]["_headerCache"]:
            for k in conf["viur.security.contentSecurityPolicy"]["_headerCache"]:
                if not k.startswith("Content-Security-Policy"):
                    raise AssertionError("Got unexpected header in "
                                         "conf['viur.security.contentSecurityPolicy']['_headerCache']")
        if conf["viur.security.strictTransportSecurity"]:
            if not conf["viur.security.strictTransportSecurity"].startswith("max-age"):
                raise AssertionError("Got unexpected header in conf['viur.security.strictTransportSecurity']")
        crossDomainPolicies = {None, "none", "master-only", "by-content-type", "all"}
        if conf["viur.security.xPermittedCrossDomainPolicies"] not in crossDomainPolicies:
            raise AssertionError("conf[\"viur.security.xPermittedCrossDomainPolicies\"] "
                                 f"must be one of {crossDomainPolicies!r}")
        if conf["viur.security.xFrameOptions"] is not None and isinstance(conf["viur.security.xFrameOptions"], tuple):
            mode, uri = conf["viur.security.xFrameOptions"]
            assert mode in ["deny", "sameorigin", "allow-from"]
            if mode == "allow-from":
                assert uri is not None and (uri.lower().startswith("https://") or uri.lower().startswith("http://"))
        runStartupTasks()  # Add a deferred call to run all queued startup tasks
        i18n.initializeTranslations()
        self.init_hmac_key()

    def init_hmac_key(self):
        if conf["viur.file.hmacKey"] is None:
            from viur.core import db
            key = db.Key("viur-conf", "viur-conf")
            if not (obj := db.Get(key)):  # create a new "viur-conf"?
                logging.info("Creating new viur-conf")
                obj = db.Entity(key)

            if "hmacKey" not in obj:  # create a new hmacKey
                logging.info("Creating new hmacKey")
                obj["hmacKey"] = utils.generateRandomString(length=20)
                db.Put(obj)

            conf["viur.file.hmacKey"] = bytes(obj["hmacKey"], "utf-8")

    def __call__(self, environ: dict, start_response: Callable) -> webob.Response:
        req = webob.Request(environ)
        resp = webob.Response()
        handler = request.BrowseHandler(req, resp)

        # Set context variables
        utils.currentLanguage.set(conf["viur.defaultLanguage"])
        utils.currentRequest.set(handler)
        utils.currentSession.set(session.Session())
        utils.currentRequestData.set({})

        # Handle request
        logging.debug("icoming request")
        logging.debug(environ)
        logging.debug(start_response)
        logging.debug(req)
        logging.debug(resp)
        # handler.processRequest()

        # Unset context variables
        utils.currentLanguage.set(None)
        utils.currentRequestData.set(None)
        utils.currentSession.set(None)
        utils.currentRequest.set(None)

        return resp(environ, start_response)
