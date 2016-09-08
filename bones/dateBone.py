# -*- coding: utf-8 -*-
from server.bones import baseBone
from server import request
from time import time, mktime
from datetime import time, datetime, timedelta
import logging
try:
	import pytz
except:
	pytz = None


## Workaround for Python Bug #7980 - time.strptime not thread safe
datetime.now().strptime("2010%02d%02d"%(1,1),"%Y%m%d")
datetime.now().strftime("%Y%m%d")

class ExtendedDateTime( datetime ):
	def totimestamp( self ):
		"""Converts this DateTime-Object back into Unixtime"""
		return( int( round( mktime( self.timetuple() ) ) ) )
		 
	def strftime(self, format ):
		"""
		Provides correct localized names for directives like %a which dont get translated on GAE properly
		This currently replaces %a, %A, %b, %B, %c, %x and %X.

		:param format: String containing the Format to apply.
		:type format: str
		:returns: str
		"""
		if "%c" in format:
			format = format.replace("%c", _("const_datetimeformat") )
		if "%x" in format:
			format = format.replace("%x", _("const_dateformat") )
		if "%X" in format:
			format = format.replace("%X", _("const_timeformat") )
		if "%a" in format:
			format = format.replace( "%a", _("const_day_%s_short" % int( super( ExtendedDateTime, self ).strftime("%w") ) ) )
		if "%A" in format:
			format = format.replace( "%A", _("const_day_%s_long" % int( super( ExtendedDateTime, self ).strftime("%w") ) ) )
		if "%b" in format:
			format = format.replace( "%b", _("const_month_%s_short" % int( super( ExtendedDateTime, self ).strftime("%m") ) ) )
		if "%B" in format:
			format = format.replace( "%B", _("const_month_%s_long" % int( super( ExtendedDateTime, self ).strftime("%m") ) ) )
		return( super( ExtendedDateTime, self ).strftime( format.encode("UTF-8") ).decode("UTF-8") )

class dateBone( baseBone ):
	type = "date"

	@staticmethod
	def generageSearchWidget(target,name="DATE BONE",mode="range"):
		return ( {"name":name,"mode":mode,"target":target,"type":"date"} )


	def __init__( self,  creationMagic=False, updateMagic=False, date=True, time=True, localize=False, *args,  **kwargs ):
		"""
			Initializes a new dateBone.
			
			:param creationMagic: Use the current time as value when creating an entity; ignoring this bone if the
				entity gets updated.
			:type creationMagic: bool
			:param updateMagic: Use the current time whenever this entity is saved.
			:type updateMagic: bool
			:param date: Should this bone contain a date-information?
			:type date: bool
			:param time: Should this bone contain time information?
			:type time: bool
			:param localize: Automatically convert this time into the users timezone? Only valid if this bone
                contains date and time-information!
			:type localize: bool
		"""
		baseBone.__init__( self,  *args,  **kwargs )
		if creationMagic or updateMagic:
			self.readonly = True
			self.visible = False
		self.creationMagic = creationMagic
		self.updateMagic = updateMagic
		if not( date or time ):
			raise ValueError("Attempt to create an empty datebone! Set date or time to True!")
		if localize and not ( date and time ):
			raise ValueError("Localization is only possible with date and time!")
		self.date=date
		self.time=time
		self.localize = localize

	def fromClient( self,valuesCache, name, data ):
		"""
			Reads a value from the client.
			If this value is valid for this bone,
			store this value and return None.
			Otherwise our previous value is
			left unchanged and an error-message
			is returned.
			
			:param name: Our name in the skeleton
			:type name: str
			:param data: *User-supplied* request-data
			:type data: dict
			:returns: str or None
		"""
		if name in data.keys():
			value = data[ name ]
		else:
			value = None
		valuesCache[name] = None
		if str( value ).replace("-",  "",  1).replace(".","",1).isdigit():
			if int(value) < -1*(2**30) or int(value)>(2**31)-2:
				return( "Invalid value entered" )
			valuesCache[name] = ExtendedDateTime.fromtimestamp( float(value) )
			return( None )
		elif not self.date and self.time:
			try:
				if str( value ).count(":")>1:
					(hour, minute, second) = [int(x.strip()) for x in str( value ).split(":")]
					valuesCache[name] = time( hour=hour, minute=minute, second=second )
					return( None )
				elif str( value ).count(":")>0:
					(hour, minute) = [int(x.strip()) for x in str( value ).split(":")]
					valuesCache[name] = time( hour=hour, minute=minute )
					return( None )
				elif str( value ).replace("-",  "",  1).isdigit():
					valuesCache[name] = time( second=int(value) )
					return( None )
			except:
				return( "Invalid value entered" )
			return( False )
		elif str( value ).lower().startswith("now"):
			tmpRes = ExtendedDateTime.now()
			if len( str( value ) )>4:
				try:
					tmpRes += timedelta( seconds= int( str(value)[3:] ) )
				except:
					pass
			valuesCache[name] = tmpRes
			return( None )
		else:
			try:
				if " " in value: # Date with time
					try: #Times with seconds
						if "-" in value: #ISO Date
							valuesCache[name] = ExtendedDateTime.strptime(str( value ), "%Y-%m-%d %H:%M:%S")
						elif "/" in value: #Ami Date
							valuesCache[name] = ExtendedDateTime.strptime(str( value ), "%m/%d/%Y %H:%M:%S")
						else: # European Date
							valuesCache[name] = ExtendedDateTime.strptime(str( value ), "%d.%m.%Y %H:%M:%S")
					except:
						if "-" in value: #ISO Date
							valuesCache[name] = ExtendedDateTime.strptime(str( value ), "%Y-%m-%d %H:%M")
						elif "/" in value: #Ami Date
							valuesCache[name] = ExtendedDateTime.strptime(str( value ), "%m/%d/%Y %H:%M")
						else: # European Date
							valuesCache[name] = ExtendedDateTime.strptime(str( value ), "%d.%m.%Y %H:%M")
				else:
					if "-" in value: #ISO Date
						valuesCache[name] = ExtendedDateTime.strptime(str( value ), "%Y-%m-%d")
					elif "/" in value: #Ami Date
						valuesCache[name] = ExtendedDateTime.strptime(str( value ), "%m/%d/%Y")
					else:
						valuesCache[name] =ExtendedDateTime.strptime(str( value ), "%d.%m.%Y")
				return( None )
			except:
				return( "Invalid value entered" )
			return( "Invalid value entered" )

	def guessTimeZone(self):
		"""
		Guess the timezone the user is supposed to be in.
		If it cant be guessed, a safe default (UTC) is used
		"""
		timeZone = "UTC" # Default fallback
		try:
			#Check the local cache first
			if "timeZone" in request.current.requestData().keys():
				return( request.current.requestData()["timeZone"] )
			headers = request.current.get().request.headers
			if "X-Appengine-Country" in headers.keys():
				country = headers["X-Appengine-Country"]
			else: # Maybe local development Server - no way to guess it here
				return( timeZone )
			tzList = pytz.country_timezones[ country ]
		except: #Non-User generated request (deferred call; task queue etc), or no pytz
			return( timeZone )
		if len( tzList ) == 1: # Fine - the country has exactly one timezone
			timeZone = tzList[ 0 ]
		elif country.lower()=="us": # Fallback for the US
			timeZone = "EST"
		else: #The user is in a Country which has more than one timezone
			pass
		request.current.requestData()["timeZone"] = timeZone #Cache the result
		return( timeZone ) 

	def readLocalized(self, value ):
		"""Read a (probably localized Value) from the Client and convert it back to UTC"""
		res = value
		if 1 or not self.localize or not value or not isinstance( value, datetime) :
			return( res )
		#Nomalize the Date to UTC
		timeZone = self.guessTimeZone()
		if timeZone!="UTC" and pytz:
			utc = pytz.utc
			tz = pytz.timezone( timeZone )
			#FIXME: This is ugly as hell.
			# Parsing a Date which is inside DST of the given tz dosnt change the tz-info,
			# and normalizing the whole thing changes the other values, too
			# So we parse the whole thing, normalize it (=>get the correct DST-Settings), then replacing the parameters again
			# and pray that the DST-Settings are still valid..
			res = ExtendedDateTime(value.year, value.month, value.day, value.hour, value.minute, value.second, tzinfo=tz)
			res = tz.normalize( res ) #Figure out if its in DST or not
			res = res.replace( year=value.year, month=value.month, day=value.day, hour=value.hour, minute=value.minute, second=value.second ) #Reset the original values
			res = utc.normalize( res.astimezone( utc ) )
		return( res )

	def serialize( self, valuesCache, name, entity ):
		res = valuesCache[name]
		if res:
			res = self.readLocalized( datetime.now().strptime( res.strftime( "%d.%m.%Y %H:%M:%S" ), "%d.%m.%Y %H:%M:%S"  ) )
		entity.set( name, res, self.indexed )
		return( entity )

	def unserialize(self, valuesCache, name, expando):
		if not name in expando.keys():
			valuesCache[name] = None
			return
		valuesCache[name] = expando[ name ]
		if valuesCache[name] and (isinstance(valuesCache[name], float) or isinstance( valuesCache[name], int)):
			if self.date:
				self.setLocalized(valuesCache, name, ExtendedDateTime.fromtimestamp( valuesCache[name]))
			else:
				valuesCache[name] = time( hour=int(valuesCache[name]/60), minute=int(valuesCache[name]%60) )
		elif isinstance( valuesCache[name], datetime ):
			self.setLocalized(valuesCache, name, ExtendedDateTime.now().strptime( valuesCache[name].strftime( "%d.%m.%Y %H:%M:%S" ), "%d.%m.%Y %H:%M:%S") )
		else:
			# We got garbarge from the datastore
			valuesCache[name] = None
		return

	def setLocalized(self, valuesCache, name, value):
		""" Converts a Date read from DB (UTC) to the requesters local time"""
		valuesCache[name] = value
		if not self.localize or not value or not isinstance( value, ExtendedDateTime) :
			return
		timeZone = self.guessTimeZone()
		if timeZone!="UTC" and pytz:
			utc = pytz.utc
			tz = pytz.timezone( timeZone )
			value = tz.normalize( value.replace( tzinfo=utc).astimezone( tz ) )
		valuesCache[name] = value

	def buildDBFilter( self, name, skel, dbFilter, rawFilter, prefix=None ):
		for key in [ x for x in rawFilter.keys() if x.startswith(name) ]:
			if not self.fromClient( key, rawFilter ): #Parsing succeeded
				super( dateBone, self ).buildDBFilter( name, skel, dbFilter, {key:datetime.now().strptime( self.value.strftime( "%d.%m.%Y %H:%M:%S" ), "%d.%m.%Y %H:%M:%S"  )}, prefix=prefix )
		return( dbFilter )

	def performMagic( self, valuesCache, name, isAdd ):
		if (self.creationMagic and isAdd) or self.updateMagic:
			self.setLocalized( valuesCache, name, ExtendedDateTime.now() )
