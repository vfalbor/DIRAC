import threading
from DIRAC import gLogger, S_OK, S_ERROR
from DIRAC.Core.Base.AgentModule import AgentModule
from DIRAC.Core.Utilities.ThreadPool import ThreadPool,ThreadedJob
from DIRAC.ResourceStatusSystem.Utilities.Exceptions import *
from DIRAC.ResourceStatusSystem.Utilities.Utils import *
from DIRAC.ResourceStatusSystem.PolicySystem.PEP import PEP
from DIRAC.ResourceStatusSystem.DB.ResourceStatusDB import *
from DIRAC.ResourceStatusSystem.Policy import Configurations

AGENT_NAME = 'ResourceStatus/SeSInspectorAgent'

class SeSInspectorAgent(AgentModule):
  """ Class SeSInspectorAgent is in charge of going through Services
      table, and pass Service and Status to the PEP
  """

  def initialize(self):
    """ Standard constructor
    """
    
    try:
      try:
        self.rsDB = ResourceStatusDB()
      except RSSDBException, x:
        gLogger.error(whoRaised(x))
      except RSSException, x:
        gLogger.error(whoRaised(x))
      
      self.am_setOption( "PollingTime", 60 )
      self.ServicesToBeChecked = []
      self.ServiceNamesInCheck = []
      #self.maxNumberOfThreads = gConfig.getValue(self.section+'/NumberOfThreads',1)
      #self.threadPoolDepth = gConfig.getValue(self.section+'/ThreadPoolDepth',1)
      
      self.maxNumberOfThreads = self.am_getOption( 'maxThreadsInPool', 1 )
      #self.threadPool = ThreadPool(1,self.maxNumberOfThreads)
  
      #vedi taskQueueDirector
      self.threadPool = ThreadPool( self.am_getOption('minThreadsInPool'),
                         self.am_getOption('maxThreadsInPool'),
                         self.am_getOption('totalThreadsInPool') )
      if not self.threadPool:
        self.log.error('Can not create Thread Pool:')
        return
      
      self.lockObj = threading.RLock()
      
      return S_OK()
    
    except Exception, x:
      errorStr = where(self, self.execute)
      gLogger.exception(errorStr,lException=x)
      return S_ERROR(errorStr)


  def execute(self):
    """ The main SSInspectorAgent execution method
    """
    
    try:
      sitesGetter = ThreadedJob(self._getServicesToCheck)
      self.threadPool.queueJob(sitesGetter)
      
      #for i in range(self.threadPoolDepth - 2):
      for i in range(self.maxNumberOfThreads - 1):
        checkExecutor = ThreadedJob(self._executeCheck)
        self.threadPool.queueJob(checkExecutor)
    
      self.threadPool.processResults()
      return S_OK()

    except Exception, x:
      errorStr = where(self, self.execute)
      gLogger.exception(errorStr,lException=x)
      return S_ERROR(errorStr)
      
  def _getServicesToCheck(self):
    """ 
    Call :meth:`DIRAC.ResourceStatusSystem.DB.ResourceStatusDB.getServicesToCheck` and put result in list
    """
    
    try:
      res = self.rsDB.getServicesToCheck(Configurations.ACTIVE_CHECK_FREQUENCY, Configurations.PROBING_CHECK_FREQUENCY, Configurations.BANNED_CHECK_FREQUENCY)
    except RSSDBException, x:
      gLogger.error(whoRaised(x))
    except RSSException, x:
      gLogger.error(whoRaised(x))

    for siteTuple in res:
      if siteTuple[0] in self.ServiceNamesInCheck:
        break
      siteL = ['Service']
      for x in siteTuple:
        siteL.append(x)
      self.lockObj.acquire()
      try:
        self.ServiceNamesInCheck.insert(0, siteL[1])
        self.ServicesToBeChecked.insert(0, siteL)
      finally:
        self.lockObj.release()


  def _executeCheck(self):
    """ 
    Create instance of a PEP, instantiated popping a site from lists.
    """
    
    if len(self.ServicesToBeChecked) > 0:
        
      self.lockObj.acquire()
      try:
        toBeChecked = self.ServicesToBeChecked.pop()
      finally:
        self.lockObj.release()
      
      granularity = toBeChecked[0]
      siteName = toBeChecked[1]
      status = toBeChecked[2]
      formerStatus = toBeChecked[3]
      reason = toBeChecked[4]
      
      newPEP = PEP(granularity = granularity, name = siteName, status = status, formerStatus = formerStatus, reason = reason)
      newPEP.enforce()

      self.lockObj.acquire()
      try:
        self.ServiceNamesInCheck.remove(siteName)
      finally:
        self.lockObj.release()