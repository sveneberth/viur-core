# -*- coding: utf-8 -*-

import string
from encodings import idna
from typing import Union

from viur.core.bones import stringBone


def validateEmail(value: str) -> Union[str, None]:
	if not value:
		return "No value entered"

	try:
		assert len(value) < 256
		account, domain = value.split("@")
		subDomain, tld = domain.rsplit(".", 1)
		assert account and subDomain and tld
		assert subDomain[0] != "."
		assert len(account) <= 64
	except:
		return "Invalid email entered"

	isValid = True

	# DoubleDotSequence
	if ".." in value:
		isValid = False

	validChars = string.ascii_letters + string.digits + "!#$%&'*+-/=?^_`{|}~."
	unicodeLowerBound = "\u0080"
	unicodeUpperBound = "\U0010FFFF"
	for char in account:
		if not (char in validChars or (char >= unicodeLowerBound and char <= unicodeUpperBound)):
			isValid = False

	try:
		idna.ToASCII(subDomain)
		idna.ToASCII(tld)
	except:
		isValid = False

	if " " in subDomain or " " in tld:
		isValid = False

	if isValid:
		return None
	else:
		return "Invalid email entered"


class emailBone(stringBone):
	type = "str.email"

	def isInvalid(self, value: str) -> Union[str, None]:
		return validateEmail(value)
