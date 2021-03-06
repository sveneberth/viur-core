# -*- coding: utf-8 -*-
from viur.core.bones import *
from viur.core import db
from xml.dom import minidom
from datetime import datetime, date, time


def serializeXML(data):
	def recursiveSerializer(data, element):
		if isinstance(data, dict):
			element.setAttribute('ViurDataType', 'dict')
			for key in data.keys():
				docElem = doc.createElement("entry")
				docElem.setAttribute('KeyName', str(key))
				childElement = recursiveSerializer(data[key], docElem)
				element.appendChild(childElement)
		elif isinstance(data, (tuple, list)):
			element.setAttribute('ViurDataType', 'list')
			for value in data:
				childElement = recursiveSerializer(value, doc.createElement('entry'))
				element.appendChild(childElement)
		else:
			if isinstance(data, bool):
				element.setAttribute('ViurDataType', 'boolean')
			elif isinstance(data, float) or isinstance(data, int):
				element.setAttribute('ViurDataType', 'numeric')
			elif isinstance(data, str):
				element.setAttribute('ViurDataType', 'string')
			elif isinstance(data, datetime) or isinstance(data, date) or isinstance(data, time):
				if isinstance(data, datetime):
					element.setAttribute('ViurDataType', 'datetime')
				elif isinstance(data, date):
					element.setAttribute('ViurDataType', 'date')
				else:
					element.setAttribute('ViurDataType', 'time')
				data = data.isoformat()
			elif isinstance(data, db.KeyClass):
				element.setAttribute('ViurDataType', 'dbkey')
				data = data.to_legacy_urlsafe().decode("ASCII")
			elif data is None:
				element.setAttribute('ViurDataType', 'none')
				data = ""
			else:
				raise NotImplementedError("Type %s is not supported!" % type(data))
			element.appendChild(doc.createTextNode(str(data)))
		return element

	dom = minidom.getDOMImplementation()
	doc = dom.createDocument(None, u"ViurResult", None)
	elem = doc.childNodes[0]
	return recursiveSerializer(data, elem).toprettyxml(encoding="UTF-8")


class DefaultRender(object):
	kind = "xml"

	def __init__(self, parent=None, *args, **kwargs):
		super(DefaultRender, self).__init__(*args, **kwargs)

	def renderBoneStructure(self, bone):
		"""
		Renders the structure of a bone.

		This function is used by :func:`renderSkelStructure`.
		can be overridden and super-called from a custom renderer.

		:param bone: The bone which structure should be rendered.
		:type bone: Any bone that inherits from :class:`server.bones.base.baseBone`.

		:return: A dict containing the rendered attributes.
		:rtype: dict
		"""

		# Base bone contents.
		ret = {
			"descr": str(bone.descr),
			"type": bone.type,
			"required": bone.required,
			"params": bone.params,
			"visible": bone.visible,
			"readOnly": bone.readOnly
		}

		if bone.type == "relational" or bone.type.startswith("relational."):
			ret.update({
				"type": "%s.%s" % (bone.type, bone.kind),
				"module": bone.module,
				"format": bone.format,
				"using": self.renderSkelStructure(bone.using()) if bone.using else None,
				"relskel": self.renderSkelStructure(bone._refSkelCache())
			})

		elif isinstance(bone, selectBone):
			ret.update({
				"values": bone.values,
				"multiple": bone.multiple
			})

		elif isinstance(bone, dateBone):
			ret.update({
				"date": bone.date,
				"time": bone.time
			})

		elif isinstance(bone, numericBone):
			ret.update({
				"precision": bone.precision,
				"min": bone.min,
				"max": bone.max
			})

		elif isinstance(bone, textBone):
			ret.update({
				"validHtml": bone.validHtml,
				"languages": bone.languages
			})

		elif isinstance(bone, stringBone):
			ret.update({
				"languages": bone.languages
			})

		return ret

	def renderSkelStructure(self, skel):
		"""
		Dumps the structure of a :class:`server.db.skeleton.Skeleton`.

		:param skel: Skeleton which structure will be processed.
		:type skel: server.db.skeleton.Skeleton

		:returns: The rendered dictionary.
		:rtype: dict
		"""
		if isinstance(skel, dict):
			return None
		res = {}
		for key, bone in skel.items():
			res[key] = self.renderBoneStructure(bone)
		return res

	def renderTextExtension(self, ext):
		e = ext()
		return ({"name": e.name,
				 "descr": str(e.descr),
				 "skel": self.renderSkelStructure(e.dataSkel())})

	def renderBoneValue(self, bone, skel, key):
		boneVal = skel[key]
		if bone.languages and bone.multiple:
			res = {}
			for language in bone.languages:
				if boneVal and language in boneVal and boneVal[language]:
					res[language] = [self.renderSingleBoneValue(v, bone, skel, key) for v in boneVal[language]]
				else:
					res[language] = []
		elif bone.languages:
			res = {}
			for language in bone.languages:
				if boneVal and language in boneVal and boneVal[language]:
					res[language] = self.renderSingleBoneValue(boneVal[language], bone, skel, key)
				else:
					res[language] = None
		elif bone.multiple:
			res = [self.renderSingleBoneValue(v, bone, skel, key) for v in boneVal] if boneVal else None
		else:
			res = self.renderSingleBoneValue(boneVal, bone, skel, key)
		return res

	def renderSingleBoneValue(self, value, bone, skel, key):
		"""
		Renders the value of a bone.

		This function is used by :func:`collectSkelData`.
		It can be overridden and super-called from a custom renderer.

		:param bone: The bone which value should be rendered.
		:type bone: Any bone that inherits from :class:`server.bones.base.baseBone`.

		:return: A dict containing the rendered attributes.
		:rtype: dict
		"""
		if isinstance(bone, dateBone):
			if value:
				if bone.date and bone.time:
					return value.strftime("%d.%m.%Y %H:%M:%S")
				elif bone.date:
					return value.strftime("%d.%m.%Y")
				return value.strftime("%H:%M:%S")
		elif isinstance(bone, relationalBone):
			if isinstance(value, list):
				tmpList = []
				for k in value:
					tmpList.append({
						"dest": self.renderSkelValues(k["dest"]),
						"rel": self.renderSkelValues(k.get("rel"))
					})
				return tmpList
			elif isinstance(value, dict):
				return {
					"dest": self.renderSkelValues(value["dest"]),
					"rel": self.renderSkelValues(value.get("rel"))
				}
		elif isinstance(bone, passwordBone):
			return ""
		else:
			return value

	def renderSkelValues(self, skel):
		"""
		Prepares values of one :class:`server.db.skeleton.Skeleton` or a list of skeletons for output.

		:param skel: Skeleton which contents will be processed.
		:type skel: server.db.skeleton.Skeleton

		:returns: A dictionary or list of dictionaries.
		:rtype: dict
		"""
		if skel is None:
			return None
		elif isinstance(skel, dict):
			return skel

		res = {}
		for key, bone in skel.items():
			res[key] = self.renderBoneValue(bone, skel, key)

		return res

	def renderEntry(self, skel, action, params=None):
		res = {
			"action": action,
			"params": params,
			"values": self.renderSkelValues(skel),
			"structure": self.renderSkelStructure(skel),
			"errors": [{"severity": x.severity.value, "fieldPath": x.fieldPath, "errorMessage": x.errorMessage,
						"invalidatedFields": x.invalidatedFields} for x in skel.errors]
		}

		return serializeXML(res)

	def view(self, skel, action="view", params=None, *args, **kwargs):
		return self.renderEntry(skel, action, params)

	def add(self, skel, action="add", params=None, *args, **kwargs):
		return self.renderEntry(skel, action, params)

	def edit(self, skel, action="edit", params=None, *args, **kwargs):
		return self.renderEntry(skel, action, params)

	def list(self, skellist, action="list", tpl=None, params=None, **kwargs):
		res = {}
		skels = []

		for skel in skellist:
			skels.append(self.renderSkelValues(skel))

		res["skellist"] = skels

		if (len(skellist) > 0):
			res["structure"] = self.renderSkelStructure(skellist[0])
		else:
			res["structure"] = None

		res["action"] = action
		res["params"] = params
		res["cursor"] = skellist.getCursor()

		return serializeXML(res)

	def editSuccess(self, skel, params=None, **kwargs):
		return (serializeXML("OKAY"))

	def addSuccess(self, skel, params=None, **kwargs):
		return (serializeXML("OKAY"))

	def addDirSuccess(self, rootNode, path, dirname, params=None, *args, **kwargs):
		return (serializeXML("OKAY"))

	def renameSuccess(self, rootNode, path, src, dest, params=None, *args, **kwargs):
		return (serializeXML("OKAY"))

	def copySuccess(self, srcrepo, srcpath, name, destrepo, destpath, type, deleteold, params=None, *args, **kwargs):
		return (serializeXML("OKAY"))

	def deleteSuccess(self, skel, params=None, *args, **kwargs):
		return (serializeXML("OKAY"))

	def reparentSuccess(self, obj, tpl=None, params=None, *args, **kwargs):
		return (serializeXML("OKAY"))

	def setIndexSuccess(self, obj, tpl=None, params=None, *args, **kwargs):
		return (serializeXML("OKAY"))

	def cloneSuccess(self, tpl=None, params=None, *args, **kwargs):
		return (serializeXML("OKAY"))
