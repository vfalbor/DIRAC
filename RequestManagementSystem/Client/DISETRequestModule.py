# $HeadURL$

""" DISET Request Module is used together with the Workflow based request
    to encapsulate generic DISET service calls
"""

__RCSID__ = "$Id$"

from DIRAC.Core.DISET.RPCClient      import RPCClient
from DIRAC                           import gConfig, gLogger, S_OK, S_ERROR

import os,sys,re

class DISETRequestModule(object):

  def __init__(self):
    # constructor code
    self.version = __RCSID__
    self.log = gLogger.getSubLogger('DISETRequest')
    self.portalEnv = False

  def execute(self):
    # main execution function
    self.log.verbose('---------------------------------------------------------------')
    self.log.info('Executing request %s' % self.RequestName)
    self.log.verbose('RequestModule version: %s' %(self.version))
    self.log.verbose('Request Type: %s' %(self.RequestType))
    self.log.verbose( '---------------------------------------------------------------')

    if self.portalEnv:
      client = RPCClient(self.TargetComponent,useCertificates=True,delegatedDN=self.OwnerDN,
                        delegatedGroup=self.OwnerGroup)

    else:
      client = RPCClient(self.Service,timeout=120)

    timeStamp = self.CreationTime
    method = self.Call
    arguments = []
    if self.Arguments != "None":
      arguments = self.Arguments.split(':::')

    result = eval('client.'+method+'('+','.join(arguments)+')')
    print result
    return result


