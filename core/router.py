# noinspection PyUnresolvedReferences
from types import ModuleType
from typing import Callable, Dict, Union

import webob

# noinspection PyUnresolvedReferences
from viur.core import logging as viurLogging, logging as viurLogging, request, session, \
    utils  # unused import, must exist, initializes request logging; unused import, must exist, initializes request logging
from viur.core.config import conf
from viur.core.module import Module
from viur.core.tasks import TaskHandler


class Router:
    def __init__(self, modules: Union[object, ModuleType], render: Union[ModuleType, Dict] = None,
                 default: str = "html"):
        super().__init__()
        self.router = {}
        self.modules = modules
        self.render = render
        self.render = default

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
        handler.processRequest()

        # Unset context variables
        utils.currentLanguage.set(None)
        utils.currentRequestData.set(None)
        utils.currentSession.set(None)
        utils.currentRequest.set(None)

        return resp(environ, start_response)

    def mapModule(self, moduleObj: object, moduleName: str, targetResolverRender: dict):
        """
            Maps each function that's exposed of moduleObj into the branch of `prop:viur.core.conf["viur.mainResolver"]`
            that's referenced by `prop:targetResolverRender`. Will also walk `prop:_viurMapSubmodules` if set
            and map these sub-modules also.
        """
        moduleFunctions = {}
        for key in [x for x in dir(moduleObj) if x[0] != "_"]:
            prop = getattr(moduleObj, key)
            if key == "canAccess" or getattr(prop, "exposed", None):
                moduleFunctions[key] = prop
        for lang in conf["viur.availableLanguages"] or [conf["viur.defaultLanguage"]]:
            # Map the module under each translation
            if "seoLanguageMap" in dir(moduleObj) and lang in moduleObj.seoLanguageMap:
                translatedModuleName = moduleObj.seoLanguageMap[lang]
                if translatedModuleName not in targetResolverRender:
                    targetResolverRender[translatedModuleName] = {}
                for fname, fcall in moduleFunctions.items():
                    targetResolverRender[translatedModuleName][fname] = fcall
                    # Map translated function names
                    if getattr(fcall, "seoLanguageMap", None) and lang in fcall.seoLanguageMap:
                        targetResolverRender[translatedModuleName][fcall.seoLanguageMap[lang]] = fcall
                if "_viurMapSubmodules" in dir(moduleObj):
                    # Map any Functions on deeper nested function
                    subModules = moduleObj._viurMapSubmodules
                    for subModule in subModules:
                        obj = getattr(moduleObj, subModule, None)
                        if obj:
                            mapModule(obj, subModule, targetResolverRender[translatedModuleName])
        if moduleName == "index":
            targetFunctionLevel = targetResolverRender
        else:
            # Map the module also under it's original name
            if moduleName not in targetResolverRender:
                targetResolverRender[moduleName] = {}
            targetFunctionLevel = targetResolverRender[moduleName]
        for fname, fcall in moduleFunctions.items():
            targetFunctionLevel[fname] = fcall
            # Map translated function names
            if getattr(fcall, "seoLanguageMap", None):
                for translatedFunctionName in fcall.seoLanguageMap.values():
                    targetFunctionLevel[translatedFunctionName] = fcall
        if "_viurMapSubmodules" in dir(moduleObj):
            # Map any Functions on deeper nested function
            subModules = moduleObj._viurMapSubmodules
            for subModule in subModules:
                obj = getattr(moduleObj, subModule, None)
                if obj:
                    mapModule(obj, subModule, targetFunctionLevel)

    def buildApp(self, modules: Union[ModuleType, object], renderers: Union[ModuleType, Dict], default: str = None):
        """
            Creates the application-context for the current instance.

            This function converts the classes found in the *modules*-module,
            and the given renders into the object found at ``conf["viur.mainApp"]``.

            Every class found in *modules* becomes

            - instanced
            - get the corresponding renderer attached
            - will be attached to ``conf["viur.mainApp"]``

            :param modules: Usually the module provided as *modules* directory within the application.
            :param renderers: Usually the module *viur.core.renders*, or a dictionary renderName => renderClass.
            :param default: Name of the renderer, which will form the root of the application.
                This will be the renderer, which wont get a prefix, usually html.
                (=> /user instead of /html/user)
        """

        class ExtendableObject(object):
            pass

        if not isinstance(renderers, dict):
            # build up the dict from viur.core.render
            renderers, renderRootModule = {}, renderers
            for key, renderModule in vars(renderRootModule).items():
                if "__" not in key:
                    renderers[key] = {}
                    for subkey, render in vars(renderModule).items():
                        if "__" not in subkey:
                            renderers[key][subkey] = render
            del renderRootModule
        if hasattr(modules, "index"):
            if issubclass(modules.index, Module):
                root = modules.index("index", "")
            else:
                root = modules.index()  # old style for backward compatibility
        else:
            root = ExtendableObject()
        modules._tasks = TaskHandler
        from viur.core.modules.moduleconf import \
            ModuleConf  # noqa: E402 # import works only here because circular imports
        modules._moduleconf = ModuleConf
        resolverDict = {}
        indexes = load_indexes_from_file()
        for moduleName, moduleClass in vars(modules).items():  # iterate over all modules
            if moduleName == "index":
                mapModule(root, "index", resolverDict)
                if isinstance(root, Module):
                    root.render = renderers[default]["default"](parent=root)
                continue
            for renderName, render in renderers.items():  # look, if a particular render should be built
                if getattr(moduleClass, renderName, False) is True:
                    modulePath = "%s/%s" % ("/" + renderName if renderName != default else "", moduleName)
                    moduleInstance = moduleClass(moduleName, modulePath)
                    # Attach the module-specific or the default render
                    moduleInstance.render = render.get(moduleName, render["default"])(parent=moduleInstance)
                    moduleInstance.indexes = indexes.get(moduleName, [])
                    if renderName == default:  # default or render (sub)namespace?
                        setattr(root, moduleName, moduleInstance)
                        targetResolverRender = resolverDict
                    else:
                        if getattr(root, renderName, True) is True:
                            # Render is not build yet, or it is just the simple marker that a given render should be build
                            setattr(root, renderName, ExtendableObject())
                        # Attach the module to the given renderer node
                        setattr(getattr(root, renderName), moduleName, moduleInstance)
                        targetResolverRender = resolverDict.setdefault(renderName, {})
                    mapModule(moduleInstance, moduleName, targetResolverRender)
                    # Apply Renderers postProcess Filters
                    if "_postProcessAppObj" in render:
                        render["_postProcessAppObj"](targetResolverRender)
            if hasattr(moduleClass, "seoLanguageMap"):
                conf["viur.languageModuleMap"][moduleName] = moduleClass.seoLanguageMap
        conf["viur.mainResolver"] = resolverDict

        if conf["viur.debug.traceExternalCallRouting"] or conf["viur.debug.traceInternalCallRouting"]:
            from viur.core import email
            try:
                email.sendEMailToAdmins("Debug mode enabled",
                                        "ViUR just started a new Instance with calltracing enabled! This will log sensitive information!")
            except:  # OverQuota, whatever
                pass  # Dont render this instance unusable
        if default in renderers and hasattr(renderers[default]["default"], "renderEmail"):
            conf["viur.emailRenderer"] = renderers[default]["default"]().renderEmail
        elif "html" in renderers:
            conf["viur.emailRenderer"] = renderers["html"]["default"]().renderEmail

        return root
