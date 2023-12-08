"""
This module provides translation, also known as internationalization -- short: i18n.

Project translations must be stored in the datastore. There are only some
static translation tables in the viur-core to have some basic ones.

The viur-core's own "translation" module (routed as _translation) provides
an API to manage these translations, for example in the vi-admin.

How to use translations?
First, make sure that the languages are configured:
.. code-block:: python
    from viur.core.config import conf
    # These are the main languages (for which translated values exist)
    # that should be available for the project.
    conf.i18n.available_languages = = ["en", "de", "fr"]

    # These are some aliases for languages that should use the translated
    # values of a particular main language, but don't have their own values.
    conf.i18n.language_alias_map = {
        "at": "de",  # Austria uses German
        "ch": "de",  # Switzerland uses German
        "be": "fr",  # Belgian uses France
        "us": "en",  # US uses English
    }

Now translations can be used

1. In python
.. code-block:: python
    from viur.core.i18n import translate
    # Just the translation key, the minimal case
    print(translate("translation-key"))
    # also provide a default value to use if there's no value in the datastore
    # set and a hint to provide some context.
    print(translate("translation-key", "the default value", "a hint"))
    # Use string interpolation with variables
    print(translate("hello", "Hello {{name}}!", "greeting a user")(name=current.user.get()["firstname"]))

2. In jinja
.. code-block:: jinja
    {# Use the ViUR translation extension, it can be compiled with the template,
       caches the translation values and is therefore efficient #}
    {% do translate "hello", "Hello {{name}}!", "greet a user", name="ViUR" %}

   {# But in some cases the key or interpolation variables are dynamic and
      not available during template compilation.
      For this you can use the translate function: #}
    {{ translate("hello", "Hello {{name}}!", "greet a user", name=skel["firstname"]) }}


How to add translations
There are two ways to add translations:
1. Manually
With the vi-admin. Entries can be added manually by creating a new skeleton
and filling in of the key and values.

2. Automatically
The add_missing_translations option must be enabled for this.
.. code-block:: python

    from viur.core.config import conf
    conf.i18n.add_missing_translations = True


If a translation is now printed and the key is unknown (because someone has
just added the related print code), an entry is added in the datastore kind.
In addition, the default text and the hint are filled in and the filename
and the line from the call from the code are set in the skeleton.
This is the recommended way, as ViUR collects all the information you need
and you only have to enter the translated values.
(3. own way
Of course you can create skeletons / entries in the datastore in your project
on your own. Just use the TranslateSkel).
"""
# FIXME: grammar, rst syntax


import datetime
import logging
import traceback
import typing as t

import jinja2.ext as jinja2
import time

from viur.core import current, db, languages, tasks
from viur.core.config import conf

systemTranslations = {}
"""Memory storage for translation methods"""

KINDNAME = "viur-translations"
"""Kindname for the translations"""


class LanguageWrapper(dict):
    """
    Wrapper-class for a multi-language value.

    It's a dictionary, allowing accessing each stored language,
    but can also be used as a string, in which case it tries to
    guess the correct language.
    Used by the HTML renderer to provide multi-lang bones values for templates.
    """

    def __init__(self, languages: list[str] | tuple[str]):
        """
        :param languages: Languages which are set in the bone.
        """
        super(LanguageWrapper, self).__init__()
        self.languages = languages

    def __str__(self) -> str:
        return str(self.resolve())

    def __bool__(self) -> bool:
        # Overridden to support if skel["bone"] tests in html render
        # (otherwise that test is always true as this dict contains keys)
        return bool(str(self))

    def resolve(self) -> str:
        """
        Causes this wrapper to evaluate to the best language available for the current request.

        :returns: An item stored inside this instance or the empty string.
        """
        lang = current.language.get()
        if lang:
            lang = conf.i18n.language_alias_map.get(lang, lang)
        else:
            logging.warning(f"No lang set to current! {lang = }")
            lang = self.languages[0]
        if (value := self.get(lang)) and str(value).strip():
            # The site language is available and not empty
            return value
        else:  # Choose the first not-empty value as alternative
            for lang in self.languages:
                if (value := self.get(lang)) and str(value).strip():
                    return value
        return ""  # TODO: maybe we should better use sth like None or N/A


class translate:
    """
    Translate class which chooses the correct translation according to the request language

    This class is the replacement for the old translate() function provided by ViUR2.  This classes __init__
    takes the unique translation key (a string usually something like "user.auth_user_password.loginfailed" which
    uniquely defines this text fragment), a default text that will be used if no translation for this key has been
    added yet (in the projects default language) and a hint (an optional text that can convey context information
    for the persons translating these texts - they are not shown to the end-user). This class will resolve its
    translations upfront, so the actual resolving (by casting this class to string) is fast. This resolves most
    translation issues with bones, which can now take an instance of this class as it's description/hints.
    """

    __slots__ = ["key", "defaultText", "hint", "translationCache", "force_lang"]

    def __init__(self, key: str, defaultText: str = None, hint: str = None, force_lang: str = None):
        """
        :param key: The unique key defining this text fragment.
            Usually it's a path/filename and a unique descriptor in that file
        :param defaultText: The text to use if no translation has been added yet.
            While optional, it's recommended to set this, as the key is used
             instead if neither are available.
        :param hint: A text only shown to the person translating this text,
            as the key/defaultText may have different meanings in the
            target language.
        :param force_lang: Use this language instead the one of the request.
        """
        super().__init__()
        key = str(key)  # ensure key is a str
        self.key = key.lower()
        self.defaultText = defaultText or key
        self.hint = hint
        self.translationCache = None
        self.force_lang = force_lang

    def __repr__(self) -> str:
        return f"<translate object for {self.key} with force_lang={self.force_lang}>"

    def __str__(self) -> str:
        if self.translationCache is None:
            global systemTranslations

            from viur.core.render.html.env.viur import translate as jinja_translate

            if self.key not in systemTranslations and conf.i18n.add_missing_translations:
                # This translation seems to be new and should be added
                filename = lineno = None
                is_jinja = False
                for frame, line in traceback.walk_stack(None):
                    if filename is None:
                        # Use the first frame as fallback.
                        # In case of calling this class directly,
                        # this is anyway the caller we're looking for.
                        filename = frame.f_code.co_filename
                        lineno = frame.f_lineno
                    if frame.f_code == jinja_translate.__code__:
                        # The call was caused by our jinja method
                        is_jinja = True
                    if is_jinja and not frame.f_code.co_filename.endswith(".py"):
                        # Look for the latest html, macro (not py) where the
                        # translate method has been used, that's our caller
                        filename = frame.f_code.co_filename
                        lineno = line
                        break

                add_missing_translation(
                    key=self.key,
                    hint=self.hint,
                    default_text=self.defaultText,
                    filename=filename,
                    lineno=lineno,
                )

            self.translationCache = self.merge_alias(systemTranslations.get(self.key, {}))

        lang = current.language.get()
        # return self.choose_translation(self.translationCache, self.defaultText, self.force_lang)
        # if (lang := self.force_lang) is None:
        #     # The default case: use the request language
        #     lang = current.language.get()
        # # Check for alias language
        # if value := self.translationCache.get(lang):
        #     return value
        # # Check the main language
        # lang = conf.i18n.language_alias_map.get(lang, lang)
        if value := self.translationCache.get(lang):
            return value
        # Use the default text from datastore or from the caller arguments
        return self.translationCache.get("_default_text_") or self.defaultText

    def translate(self, **kwargs) -> str:
        """Substitute the given kwargs in the translated or default text."""
        return self.substitute_vars(str(self), **kwargs)

    def __call__(self, **kwargs):
        """Just an alias for translate"""
        return self.translate(**kwargs)

    @staticmethod
    def choose_translation(
        translations:dict[str, str],
        default_text: str = "",
        force_lang: str|None = None,
    ):
        if (lang := force_lang) is None:
            # The default case: use the request language
            lang = current.language.get()
        # Check for alias language
        if value := translations.get(lang):
            return value
        # Check the main language
        lang = conf.i18n.language_alias_map.get(lang, lang)
        if value := translations.get(lang):
            return value
        # Use the default text from datastore or from the caller arguments
        return translations.get("_default_text_") or default_text or ""

    @staticmethod
    def substitute_vars(value:str, **kwargs):
        res = str(value)
        for k, v in kwargs.items():
            res = res.replace("{{%s}}" % k, str(v))
        return res

    @staticmethod
    def merge_alias(translations:dict[str, str]):
        # TODO custom default text?
        logging.debug(f"{translations = }")
        for alias, main in conf.i18n.language_alias_map.items():
            if not (value:=translations.get(alias)) or not value.strip():
                translations[alias] = translations.get(main) or translations.get("_default_text_")
        logging.debug(f"{translations = }")
        return translations



class TranslationExtension(jinja2.Extension):
    """
    Default translation extension for jinja2 render.
    Use like {% translate "translationKey", "defaultText", "translationHint", replaceValue1="replacedText1" %}
    All except translationKey is optional. translationKey is the same Key supplied to _() before.
    defaultText will be printed if no translation is available.
    translationHint is an optional hint for anyone adding a now translation how/where that translation is used.
    """

    tags = {"translate"}

    def parse(self, parser):
        # Parse the translate tag
        global systemTranslations
        args = []
        kwargs = {}
        lineno = parser.stream.current.lineno
        filename = parser.stream.filename
        # Parse arguments (args and kwargs) until the current block ends
        lastToken = None
        while parser.stream.current.type != 'block_end':
            lastToken = parser.parse_expression()
            if parser.stream.current.type == "comma":  # It's a positional arg
                args.append(lastToken.value)
                next(parser.stream)  # Advance pointer
                lastToken = None
            elif parser.stream.current.type == "assign":
                next(parser.stream)  # Advance beyond =
                expr = parser.parse_expression()
                kwargs[lastToken.name] = expr.value
                if parser.stream.current.type == "comma":
                    next(parser.stream)
                elif parser.stream.current.type == "block_end":
                    lastToken = None
                    break
                else:
                    raise SyntaxError()
                lastToken = None
        if lastToken:  # TODO: what's this? what it is doing?
            print(f"final append {lastToken = }")
            args.append(lastToken.value)
        if not 0 < len(args) <= 3:
            raise SyntaxError("Translation-Key missing or excess parameters!")
        args += [""] * (3 - len(args))
        args += [kwargs]
        tr_key = args[0].lower()
        if tr_key not in systemTranslations:
            add_missing_translation(
                key=tr_key,
                hint=args[1],
                default_text=args[2],
                filename=filename,
                lineno=lineno,
                variables=list(kwargs.keys()),
            )

        translations = translate.merge_alias(systemTranslations.get(tr_key, {}))
        args = [jinja2.nodes.Const(x) for x in args]
        args.append(jinja2.nodes.Const(translations))
        return jinja2.nodes.CallBlock(self.call_method("_translate", args), [], [], []).set_lineno(lineno)

    def _translate(
        self, key: str, default_text: str, hint: str, kwargs: dict[str, t.Any],
        translations: dict[str, str], caller
    ) -> str:
        """Perform the actual translation during render"""
        lang = current.language.get()
        # lang = conf.i18n.language_alias_map.get(lang, lang)
        default_text = translations.get("_default_text_") or default_text
        res = str(translations.get(lang, default_text))
        return translate.substitute_vars(res, **kwargs)


def initializeTranslations() -> None:
    """
        Fetches all translations from the datastore and populates the *systemTranslations* dictionary of this module.
        Currently, the translate-class will resolve using that dictionary; but as we expect projects to grow and
        accumulate translations that are no longer/not yet used, we plan to made the translation-class fetch it's
        translations directly from the datastore, so we don't have to allocate memory for unused translations.
    """
    start = time.perf_counter()

    # Load translations from static languages module into systemTranslations
    # If they're in the datastore, they will be overwritten below.
    for lang in dir(languages):
        if lang.startswith("__"):
            continue
        for tr_key, tr_value in getattr(languages, lang).items():
            systemTranslations.setdefault(tr_key, {})[lang] = tr_value

    # Load translations from datastore into systemTranslations
    # TODO: iter() would be more memory efficient, but unfortunately takes much longer than run()
    # for entity in db.Query(KINDNAME).iter():
    for entity in db.Query(KINDNAME).run(10_000):
        if "tr_key" not in entity:
            logging.error(f"translations entity {entity.key} has no tr_key set --> Call migration")
            migrate_translation(entity.key)
            # Before the migration has run do a quick modification to get it loaded as is
            entity["tr_key"] = entity["key"] or entity.key.name
        if not entity.get("tr_key"):
            logging.error(f'translations entity {entity.key} has an empty {entity["tr_key"]=} set. Skipping.')
            continue
        if entity and not isinstance(entity["translations"], dict):
            logging.error(f'translations entity {entity.key} has invalid '
                          f'translations set: {entity["translations"]}. Skipping.')
            continue

        translations = {
            "_default_text_": entity.get("default_text") or None,
        }
        for lang, translation in entity["translations"].items():
            if lang not in conf.i18n.available_dialects:
                # Don't store unknown languages in the memory
                continue
            translations[lang] = translation
        systemTranslations[entity["tr_key"]] = translations

    end = time.perf_counter()
    print(f"time: {end - start}s")  # TODO: remove me


@tasks.CallDeferred
@tasks.retry_n_times(20)
def add_missing_translation(
    key: str,
    hint: str | None = None,
    default_text: str | None = None,
    filename: str | None = None,
    lineno: int | None = None,
    variables: list[str] = None,
) -> None:
    """Add missing translations to datastore"""
    try:
        from viur.core.modules.translation import TranslationSkel, Creator
    except ImportError as exc:
        logging.exception(f"ImportError (probably during warmup), cannot add translation: {exc}")
        return
    # Ensure lowercase key
    key = key.lower()
    entity = db.Query(KINDNAME).filter("tr_key =", key).getEntry()
    if entity is not None:
        # Ensure it doesn't exist to avoid datastore conflicts
        logging.warning(f"Found an entity with tr_key={key}. "
                        f"Probably an other instance was faster.")
        return

    logging.info(f"Add missing translation {key}")
    skel = TranslationSkel()
    skel["tr_key"] = key
    skel["default_text"] = default_text or None
    skel["hint"] = hint or None
    skel["usage_filename"] = filename
    skel["usage_lineno"] = lineno
    skel["usage_variables"] = variables or []
    skel["creator"] = Creator.VIUR
    skel.toDB()

    # Add to system translation to avoid triggering this method again
    systemTranslations[key] = {
        "_default_text_": default_text or None,
    }


@tasks.CallDeferred
@tasks.retry_n_times(20)
def migrate_translation(
    key: db.Key,
) -> None:
    """Migrate entities in the required.

    With viur-core 3.6 translations are now managed as Skeletons and require
    some changes, which are performed in this method.
    """
    from viur.core.modules.translation import TranslationSkel
    logging.info(f"Migrate translation {key}")
    entity: db.Entity = db.Get(key)
    if "tr_key" not in entity:
        entity["tr_key"] = entity["key"] or key.name
    if "translation" in entity:
        if not isinstance(dict, entity["translation"]):
            logging.error("translation is not a dict?")
        entity["translation"]["_viurLanguageWrapper_"] = True
    skel = TranslationSkel()
    skel.setEntity(entity)
    skel["key"] = key
    try:
        skel.toDB()
    except ValueError as exc:
        logging.exception(exc)
        if "unique value" in exc.args[0] and "recently claimed" in exc.args[0]:
            logging.info(f"Delete duplicate entry {key}: {entity}")
            db.Delete(key)
        else:
            raise exc


localizedDateTime = translate("const_datetimeformat", "%a %b %d %H:%M:%S %Y", "Localized Time and Date format string")
localizedDate = translate("const_dateformat", "%m/%d/%Y", "Localized Date only format string")
localizedTime = translate("const_timeformat", "%H:%M:%S", "Localized Time only format string")
localizedAbbrevDayNames = {
    0: translate("const_day_0_short", "Sun", "Abbreviation for Sunday"),
    1: translate("const_day_1_short", "Mon", "Abbreviation for Monday"),
    2: translate("const_day_2_short", "Tue", "Abbreviation for Tuesday"),
    3: translate("const_day_3_short", "Wed", "Abbreviation for Wednesday"),
    4: translate("const_day_4_short", "Thu", "Abbreviation for Thursday"),
    5: translate("const_day_5_short", "Fri", "Abbreviation for Friday"),
    6: translate("const_day_6_short", "Sat", "Abbreviation for Saturday"),
}
localizedDayNames = {
    0: translate("const_day_0_long", "Sunday", "Sunday"),
    1: translate("const_day_1_long", "Monday", "Monday"),
    2: translate("const_day_2_long", "Tuesday", "Tuesday"),
    3: translate("const_day_3_long", "Wednesday", "Wednesday"),
    4: translate("const_day_4_long", "Thursday", "Thursday"),
    5: translate("const_day_5_long", "Friday", "Friday"),
    6: translate("const_day_6_long", "Saturday", "Saturday"),
}
localizedAbbrevMonthNames = {
    1: translate("const_month_1_short", "Jan", "Abbreviation for January"),
    2: translate("const_month_2_short", "Feb", "Abbreviation for February"),
    3: translate("const_month_3_short", "Mar", "Abbreviation for March"),
    4: translate("const_month_4_short", "Apr", "Abbreviation for April"),
    5: translate("const_month_5_short", "May", "Abbreviation for May"),
    6: translate("const_month_6_short", "Jun", "Abbreviation for June"),
    7: translate("const_month_7_short", "Jul", "Abbreviation for July"),
    8: translate("const_month_8_short", "Aug", "Abbreviation for August"),
    9: translate("const_month_9_short", "Sep", "Abbreviation for September"),
    10: translate("const_month_10_short", "Oct", "Abbreviation for October"),
    11: translate("const_month_11_short", "Nov", "Abbreviation for November"),
    12: translate("const_month_12_short", "Dec", "Abbreviation for December"),
}
localizedMonthNames = {
    1: translate("const_month_1_long", "January", "January"),
    2: translate("const_month_2_long", "February", "February"),
    3: translate("const_month_3_long", "March", "March"),
    4: translate("const_month_4_long", "April", "April"),
    5: translate("const_month_5_long", "May", "May"),
    6: translate("const_month_6_long", "June", "June"),
    7: translate("const_month_7_long", "July", "July"),
    8: translate("const_month_8_long", "August", "August"),
    9: translate("const_month_9_long", "September", "September"),
    10: translate("const_month_10_long", "October", "October"),
    11: translate("const_month_11_long", "November", "November"),
    12: translate("const_month_12_long", "December", "December"),
}


def localizedStrfTime(datetimeObj: datetime.datetime, format: str) -> str:
    """
        Provides correct localized names for directives like %a which don't get translated on GAE properly as we can't
        set the locale (for each request).
        This currently replaces %a, %A, %b, %B, %c, %x and %X.

        :param datetimeObj: Datetime-instance to call strftime on
        :param format: String containing the Format to apply.
        :returns: Date and time formatted according to format with correct localization
    """
    if "%c" in format:
        format = format.replace("%c", str(localizedDateTime))
    if "%x" in format:
        format = format.replace("%x", str(localizedDate))
    if "%X" in format:
        format = format.replace("%X", str(localizedTime))
    if "%a" in format:
        format = format.replace("%a", str(localizedAbbrevDayNames[int(datetimeObj.strftime("%w"))]))
    if "%A" in format:
        format = format.replace("%A", str(localizedDayNames[int(datetimeObj.strftime("%w"))]))
    if "%b" in format:
        format = format.replace("%b", str(localizedAbbrevMonthNames[int(datetimeObj.strftime("%m"))]))
    if "%B" in format:
        format = format.replace("%B", str(localizedMonthNames[int(datetimeObj.strftime("%m"))]))
    return datetimeObj.strftime(format)
