#!/usr/bin/env python
########################################################################
# $HeadURL$
# File :    dirac-info
# Author :  Andrei Tsaregorodtsev
########################################################################
"""
  Report info about local DIRAC installation
"""
__RCSID__ = "$Id$"

from pprint import pprint
import DIRAC
from DIRAC import gConfig
from DIRAC.Core.Base import Script
from DIRAC.ConfigurationSystem.Client.Helpers                import getVO

Script.setUsageMessage( '\n'.join( [ __doc__.split( '\n' )[1],
                                     'Usage:',
                                     '  %s [option|cfgfile] ... Site' % Script.scriptName, ] ) )
Script.parseCommandLine( ignoreErrors = True )
args = Script.getPositionalArgs()

infoDict = {}

infoDict['Setup'] = gConfig.getValue( '/DIRAC/Setup', 'Unknown' )
infoDict['ConfigurationServer'] = gConfig.getValue( '/DIRAC/Configuration/Servers', [] )
infoDict['VirtualOrganization'] = getVO( 'Unknown' )

print 'DIRAC version'.rjust( 20 ), ':', DIRAC.version

for k, v in infoDict.items():
  print k.rjust( 20 ), ':', str( v )
