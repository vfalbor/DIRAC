########################################################################
# $Header: /tmp/libdirac/tmp.FKduyw2449/dirac/DIRAC3/DIRAC/StorageManagementSystem/DB/StagerDB.py,v 1.3 2009/11/03 16:06:29 acsmith Exp $
########################################################################

""" StorageManagementDB is a front end to the Stager Database.

    There are five tables in the StorageManagementDB: Tasks, CacheReplicas, TaskReplicas, StageRequests.

    The Tasks table is the place holder for the tasks that have requested files to be staged. These can be from different systems and have different associated call back methods.
    The CacheReplicas table keeps the information on all the CacheReplicas in the system. It maps all the file information LFN, PFN, SE to an assigned ReplicaID.
    The TaskReplicas table maps the TaskIDs from the Tasks table to the ReplicaID from the CacheReplicas table.
    The StageRequests table contains each of the prestage request IDs for each of the replicas.
"""

__RCSID__ = "$Id$"

from DIRAC                                        import gLogger, gConfig, S_OK, S_ERROR
from DIRAC.Core.Base.DB                           import DB
from DIRAC.Core.Utilities.List                    import intListToString, stringListToString
from DIRAC.Core.Utilities.Time                    import toString
import string, threading, types
import inspect
from sets import Set

class StorageManagementDB( DB ):

  def __init__( self, systemInstance = 'Default', maxQueueSize = 10 ):
    DB.__init__( self, 'StorageManagementDB', 'StorageManagement/StorageManagementDB', maxQueueSize )
    self.lock = threading.Lock()
    self.TASKPARAMS = ['TaskID', 'Status', 'Source', 'SubmitTime', 'LastUpdate', 'CompleteTime', 'CallBackMethod', 'SourceTaskID']
    self.REPLICAPARAMS = ['ReplicaID', 'Type', 'Status', 'SE', 'LFN', 'PFN', 'Size', 'FileChecksum', 'GUID', 'SubmitTime', 'LastUpdate', 'Reason', 'Links']
    self.STAGEPARAMS = ['ReplicaID', 'StageStatus', 'RequestID', 'StageRequestSubmitTime', 'StageRequestCompletedTime', 'PinLength', 'PinExpiryTime']

  def __getConnection( self, connection ):
    if connection:
      return connection
    res = self._getConnection()
    if res['OK']:
      return res['Value']
    gLogger.warn( "Failed to get MySQL connection", res['Message'] )
    return connection

  def _caller( self ):
    return inspect.stack()[2][3]
  ################################################################
  #
  # State machine management
  #

  def updateTaskStatus( self, taskIDs, newTaskStatus, connection = False ):
    return self.__updateTaskStatus( taskIDs, newTaskStatus, connection = connection )

  def __updateTaskStatus( self, taskIDs, newTaskStatus, force = False, connection = False ):
    connection = self.__getConnection( connection )
    if not taskIDs:
      return S_OK( taskIDs )
    if force:
      toUpdate = taskIDs
    else:
      res = self._checkTaskUpdate( taskIDs, newTaskStatus, connection = connection )
      if not res['OK']:
        return res
      toUpdate = res['Value']
    if not toUpdate:
      return S_OK( toUpdate )

    reqSelect = "SELECT * FROM Tasks WHERE TaskID IN (%s) AND Status != '%s';" % ( intListToString( toUpdate ), newTaskStatus )
    resSelect = self._query( reqSelect, connection )
    if not resSelect['OK']:
      gLogger.error( "%s.%s_DB: problem retrieving record: %s. %s" % ( self._caller(), '__updateTaskStatus', reqSelect, resSelect['Message'] ) )

    req = "UPDATE Tasks SET Status='%s',LastUpdate=UTC_TIMESTAMP() WHERE TaskID IN (%s) AND Status != '%s';" % ( newTaskStatus, intListToString( toUpdate ), newTaskStatus )
    res = self._update( req, connection )
    if not res['OK']:
      return res

    taskIDs = []
    for record in resSelect['Value']:
      taskIDs.append( record[0] )
      gLogger.info( "%s.%s_DB: to_update Tasks =  %s" % ( self._caller(), '__updateTaskStatus', record ) )

    reqSelect1 = "SELECT * FROM Tasks WHERE TaskID IN (%s);" % intListToString( taskIDs )
    resSelect1 = self._query( reqSelect1, connection )
    if not resSelect1["OK"]:
      gLogger.info( "%s.%s_DB: problem retrieving records: %s. %s" % ( self._caller(), '__updateTaskStatus', reqSelect1, resSelect1['Message'] ) )

    for record in resSelect1['Value']:
      gLogger.info( "%s.%s_DB: updated Tasks = %s" % ( self._caller(), '__updateTaskStatus', record ) )

    return S_OK( toUpdate )

  def _checkTaskUpdate( self, taskIDs, newTaskState, connection = False ):
    connection = self.__getConnection( connection )
    if not taskIDs:
      return S_OK( taskIDs )
    # * -> Failed
    if newTaskState == 'Failed':
      oldTaskState = []
    # StageCompleting -> Done
    elif newTaskState == 'Done':
      oldTaskState = ['StageCompleting']
    # StageSubmitted -> StageCompleting
    elif newTaskState == 'StageCompleting':
      oldTaskState = ['StageSubmitted']
    # Waiting -> StageSubmitted
    elif newTaskState == 'StageSubmitted':
      oldTaskState = ['Waiting']
    # New -> Waiting
    elif newTaskState == 'Waiting':
      oldTaskState = ['New']
    else:
      return S_ERROR( "Task status not recognized" )
    if not oldTaskState:
      toUpdate = taskIDs
    else:
      req = "SELECT TaskID FROM Tasks WHERE Status in (%s) AND TaskID IN (%s)" % ( stringListToString( oldTaskState ), intListToString( taskIDs ) )
      res = self._query( req, connection )
      if not res['OK']:
        return res
      toUpdate = [row[0] for row in res['Value']]
    return S_OK( toUpdate )

  def updateReplicaStatus( self, replicaIDs, newReplicaStatus, connection = False ):
    connection = self.__getConnection( connection )
    if not replicaIDs:
      return S_OK( replicaIDs )
    res = self._checkReplicaUpdate( replicaIDs, newReplicaStatus )
    if not res['OK']:
      return res
    toUpdate = res['Value']
    if not toUpdate:
      return S_OK( toUpdate )
    reqSelect = "SELECT * FROM CacheReplicas WHERE ReplicaID IN (%s) AND Status != '%s';" % ( intListToString( toUpdate ), newReplicaStatus )
    resSelect = self._query( reqSelect, connection )
    if not resSelect['OK']:
      gLogger.error( "%s.%s_DB: problem retrieving record: %s. %s" % ( self._caller(), 'updateReplicaStatus', reqSelect, resSelect['Message'] ) )

    req = "UPDATE CacheReplicas SET Status='%s',LastUpdate=UTC_TIMESTAMP() WHERE ReplicaID IN (%s) AND Status != '%s';" % ( newReplicaStatus, intListToString( toUpdate ), newReplicaStatus )
    res = self._update( req, connection )
    if not res['OK']:
      return res

    replicaIDs = []
    for record in resSelect['Value']:
      replicaIDs.append( record[0] )
      gLogger.info( "%s.%s_DB: to_update CacheReplicas =  %s" % ( self._caller(), 'updateReplicaStatus', record ) )

    reqSelect1 = "SELECT * FROM CacheReplicas WHERE ReplicaID IN (%s);" % intListToString( replicaIDs )
    resSelect1 = self._query( reqSelect1, connection )
    if not resSelect1['OK']:
      gLogger.info( "%s.%s_DB: problem retrieving records: %s. %s" % ( self._caller(), 'updateReplicaStatus', reqSelect1, resSelect1['Message'] ) )

    for record in resSelect1['Value']:
      gLogger.info( "%s.%s_DB: updated CacheReplicas = %s" % ( self._caller(), 'updateReplicaStatus', record ) )

    # Now update the tasks associated to the replicaIDs
    # Daniela: what if some of the replicas are still in Staging state for a task?
    newTaskStatus = self.__getTaskStateFromReplicaState( newReplicaStatus )
    res = self._getReplicaTasks( toUpdate, connection = connection )
    if not res['OK']:
      return res
    taskIDs = res['Value']
    if taskIDs:
      res = self.__updateTaskStatus( taskIDs, newTaskStatus, True, connection = connection )
      if not res['OK']:
        gLogger.warn( "Failed to update tasks associated to replicas", res['Message'] )
    return S_OK( toUpdate )

  def _getReplicaTasks( self, replicaIDs, connection = False ):
    connection = self.__getConnection( connection )
    #Daniela: should select only tasks with complete replicaID sets
    #only if ALL Replicas belonging to a Task have a certain state, the task should be selected for state update
    req = "SELECT DISTINCT(TaskID) FROM TaskReplicas WHERE ReplicaID IN (%s);" % intListToString( replicaIDs )
    res = self._query( req, connection )
    if not res['OK']:
      return res
    taskIDs = [row[0] for row in res['Value']]

    # fix
    finalTaskIDs = []
    for taskID in taskIDs:
      subreq = "SELECT ReplicaID FROM CacheReplicas WHERE Status = (SELECT Status FROM Tasks WHERE TaskID = %s);" % taskID
      subres = self._query( subreq, connection )
      if not subres['OK']:
        return subres
      replicaIDsForTask = [row[0] for row in subres['Value']]
      setOriginalReplicaIDs = Set( replicaIDs )
      setReplicaIDsForTask = Set( replicaIDsForTask )
      if setReplicaIDsForTask <= setOriginalReplicaIDs:
        finalTaskIDs.append( taskID )
    #end_fix

    return S_OK( finalTaskIDs )

  def _checkReplicaUpdate( self, replicaIDs, newReplicaState, connection = False ):
    connection = self.__getConnection( connection )
    if not replicaIDs:
      return S_OK( replicaIDs )
    # * -> Failed
    if newReplicaState == 'Failed':
      oldReplicaState = []
    # New -> Waiting
    elif newReplicaState == 'Waiting':
      oldReplicaState = ['New']
    # Waiting -> StageSubmitted
    elif newReplicaState == 'StageSubmitted':
      oldReplicaState = ['Waiting']
    # StageSubmitted -> Staged
    elif newReplicaState == 'Staged':
      oldReplicaState = ['StageSubmitted']
    else:
      return S_ERROR( "Replica status not recognized" )
    if not oldReplicaState:
      toUpdate = replicaIDs
    else:
      req = "SELECT ReplicaID FROM CacheReplicas WHERE Status IN (%s) AND ReplicaID IN (%s)" % ( stringListToString( oldReplicaState ), intListToString( replicaIDs ) )
      res = self._query( req, connection )
      if not res['OK']:
        return res
      toUpdate = [row[0] for row in res['Value']]
    return S_OK( toUpdate )

  def __getTaskStateFromReplicaState( self, replicaState ):
    # For the moment the task state just references to the replicaState
    return replicaState

  def updateStageRequestStatus( self, replicaIDs, newStageStatus, connection = False ):
    connection = self.__getConnection( connection )
    if not replicaIDs:
      return S_OK( replicaIDs )
    res = self._checkStageUpdate( replicaIDs, newStageStatus, connection = connection )
    if not res['OK']:
      return res
    toUpdate = res['Value']
    if not toUpdate:
      return S_OK( toUpdate )
    reqSelect = "Select * FROM CacheReplicas WHERE ReplicaID IN (%s) AND Status != '%s';" % ( intListToString( toUpdate ), newStageStatus )
    resSelect = self._query( reqSelect, connection )
    if not resSelect['OK']:
      gLogger.info( "%s.%s_DB: problem retrieving record: %s. %s" % ( self._caller(), 'updateStageRequestStatus', reqSelect, resSelect['Message'] ) )

    req = "UPDATE CacheReplicas SET Status='%s',LastUpdate=UTC_TIMESTAMP() WHERE ReplicaID IN (%s) AND Status != '%s';" % ( newStageStatus, intListToString( toUpdate ), newStageStatus )
    res = self._update( req, connection )
    if not res['OK']:
      return res

    replicaIDs = []
    for record in resSelect['Value']:
      replicaIDs.append( record[0] )
      gLogger.info( "%s.%s_DB: to_update CacheReplicas =  %s" % ( self._caller(), 'updateStageRequestStatus', record ) )

    reqSelect1 = "SELECT * FROM CacheReplicas WHERE ReplicaID IN (%s);" % intListToString( replicaIDs )
    resSelect1 = self._query( reqSelect1, connection )
    if not resSelect1['OK']:
      gLogger.info( "%s.%s_DB: problem retrieving records: %s. %s" % ( self._caller(), 'updateStageRequestStatus', reqSelect1, resSelect1['Message'] ) )

    for record in resSelect1['Value']:
      gLogger.info( "%s.%s_DB: updated CacheReplicas = %s" % ( self._caller(), 'updateStageRequestStatus', record ) )

    # Now update the replicas associated to the replicaIDs
    newReplicaStatus = self.__getReplicaStateFromStageState( newStageStatus )
    res = self.updateReplicaStatus( toUpdate, newReplicaStatus, connection = connection )
    if not res['OK']:
      gLogger.warn( "Failed to update cache replicas associated to stage requests", res['Message'] )
    return S_OK( toUpdate )

  def _checkStageUpdate( self, replicaIDs, newStageState, connection = False ):
    connection = self.__getConnection( connection )
    if not replicaIDs:
      return S_OK( replicaIDs )
    # * -> Failed
    if newStageState == 'Failed':
      oldStageState = []
    elif newStageState == 'Staged':
      oldStageState = ['StageSubmitted']
    else:
      return S_ERROR( "StageRequest status not recognized" )
    if not oldStageState:
      toUpdate = replicaIDs
    else:
      req = "SELECT ReplicaID FROM StageRequests WHERE StageStatus = '%s' AND ReplicaID IN (%s)" % ( oldStageState, intListToString( replicaIDs ) )
      res = self._query( req, connection )
      if not res['OK']:
        return res
      toUpdate = [row[0] for row in res['Value']]
    return S_OK( toUpdate )

  def __getReplicaStateFromStageState( self, stageState ):
    # For the moment the replica state just references to the stage state
    return stageState

  #
  #                               End of state machine management
  #
  ################################################################

  ################################################################
  #
  # Monitoring of stage tasks
  #
  def getTaskStatus( self, taskID, connection = False ):
    """ Obtain the task status from the Tasks table. """
    connection = self.__getConnection( connection )
    res = self.getTaskInfo( taskID, connection = connection )
    if not res['OK']:
      return res
    taskInfo = res['Value'][taskID]
    return S_OK( taskInfo['Status'] )

  def getTaskInfo( self, taskID, connection = False ):
    """ Obtain all the information from the Tasks table for a supplied task. """
    connection = self.__getConnection( connection )
    req = "SELECT TaskID,Status,Source,SubmitTime,CompleteTime,CallBackMethod,SourceTaskID from Tasks WHERE TaskID = %s;" % taskID
    res = self._query( req, connection )
    if not res['OK']:
      gLogger.error( 'StorageManagementDB.getTaskInfo: Failed to get task information.', res['Message'] )
      return res
    resDict = {}
    for taskID, status, source, submitTime, completeTime, callBackMethod, sourceTaskID in res['Value']:
      resDict[taskID] = {'Status':status, 'Source':source, 'SubmitTime':submitTime, 'CompleteTime':completeTime, 'CallBackMethod':callBackMethod, 'SourceTaskID':sourceTaskID}
    if not resDict:
      gLogger.error( 'StorageManagementDB.getTaskInfo: The supplied task did not exist' )
      return S_ERROR( 'The supplied task did not exist' )
    return S_OK( resDict )

  def getTaskSummary( self, taskID, connection = False ):
    """ Obtain the task summary from the database. """
    connection = self.__getConnection( connection )
    res = self.getTaskInfo( taskID, connection = connection )
    if not res['OK']:
      return res
    taskInfo = res['Value']
    req = "SELECT R.LFN,R.SE,R.PFN,R.Size,R.Status,R.Reason FROM CacheReplicas AS R, TaskReplicas AS TR WHERE TR.TaskID = %s AND TR.ReplicaID=R.ReplicaID;" % taskID
    res = self._query( req, connection )
    if not res['OK']:
      gLogger.error( 'StorageManagementDB.getTaskSummary: Failed to get Replica summary for task.', res['Message'] )
      return res
    replicaInfo = {}
    for lfn, storageElement, pfn, fileSize, status, reason in res['Value']:
      replicaInfo[lfn] = {'StorageElement':storageElement, 'PFN':pfn, 'FileSize':fileSize, 'Status':status, 'Reason':reason}
    resDict = {'TaskInfo':taskInfo, 'ReplicaInfo':replicaInfo}
    return S_OK( resDict )

  def getTasks( self, condDict = {}, older = None, newer = None, timeStamp = 'SubmitTime', orderAttribute = None, limit = None, connection = False ):
    """ Get stage requests for the supplied selection with support for web standard structure """
    connection = self.__getConnection( connection )
    req = "SELECT %s FROM Tasks" % ( intListToString( self.TASKPARAMS ) )
    if condDict or older or newer:
      if condDict.has_key( 'ReplicaID' ):
        replicaIDs = condDict.pop( 'ReplicaID' )
        if type( replicaIDs ) not in ( types.ListType, types.TupleType ):
          replicaIDs = [replicaIDs]
        res = self._getReplicaIDTasks( replicaIDs, connection = connection )
        if not res['OK']:
          return res
        condDict['TaskID'] = res['Value']
      req = "%s %s" % ( req, self.buildCondition( condDict, older, newer, timeStamp, orderAttribute, limit ) )
    res = self._query( req, connection )
    if not res['OK']:
      return res
    tasks = res['Value']
    resultDict = {}
    for row in tasks:
      resultDict[row[0]] = dict( zip( self.TASKPARAMS[1:], row[1:] ) )
    result = S_OK( resultDict )
    result['Records'] = tasks
    result['ParameterNames'] = self.TASKPARAMS
    return result

  def getCacheReplicas( self, condDict = {}, older = None, newer = None, timeStamp = 'LastUpdate', orderAttribute = None, limit = None, connection = False ):
    """ Get cache replicas for the supplied selection with support for the web standard structure """
    connection = self.__getConnection( connection )
    req = "SELECT %s FROM CacheReplicas" % ( intListToString( self.REPLICAPARAMS ) )
    originalFileIDs = {}
    if condDict or older or newer:
      if condDict.has_key( 'TaskID' ):
        taskIDs = condDict.pop( 'TaskID' )
        if type( taskIDs ) not in ( types.ListType, types.TupleType ):
          taskIDs = [taskIDs]
        res = self._getTaskReplicaIDs( taskIDs, connection = connection )
        if not res['OK']:
          return res
        condDict['ReplicaID'] = res['Value']
      req = "%s %s" % ( req, self.buildCondition( condDict, older, newer, timeStamp, orderAttribute, limit ) )
    res = self._query( req, connection )
    if not res['OK']:
      return res
    cacheReplicas = res['Value']
    resultDict = {}
    for row in cacheReplicas:
      resultDict[row[0]] = dict( zip( self.REPLICAPARAMS[1:], row[1:] ) )
    result = S_OK( resultDict )
    result['Records'] = cacheReplicas
    result['ParameterNames'] = self.REPLICAPARAMS
    return result

  def getStageRequests( self, condDict = {}, older = None, newer = None, timeStamp = 'StageRequestSubmitTime', orderAttribute = None, limit = None, connection = False ):
    """ Get stage requests for the supplied selection with support for web standard structure """
    connection = self.__getConnection( connection )
    req = "SELECT %s FROM StageRequests" % ( intListToString( self.STAGEPARAMS ) )
    if condDict or older or newer:
      if condDict.has_key( 'TaskID' ):
        taskIDs = condDict.pop( 'TaskID' )
        if type( taskIDs ) not in ( types.ListType, types.TupleType ):
          taskIDs = [taskIDs]
        res = self._getTaskReplicaIDs( taskIDs, connection = connection )
        if not res['OK']:
          return res
        condDict['ReplicaID'] = res['Value']
      req = "%s %s" % ( req, self.buildCondition( condDict, older, newer, timeStamp, orderAttribute, limit ) )
    res = self._query( req, connection )
    if not res['OK']:
      return res
    stageRequests = res['Value']
    resultDict = {}
    for row in stageRequests:
      resultDict[row[0]] = dict( zip( self.STAGEPARAMS[1:], row[1:] ) )
    result = S_OK( resultDict )
    result['Records'] = stageRequests
    result['ParameterNames'] = self.STAGEPARAMS
    return result

  def _getTaskReplicaIDs( self, taskIDs, connection = False ):
    req = "SELECT ReplicaID FROM TaskReplicas WHERE TaskID IN (%s);" % intListToString( taskIDs )
    res = self._query( req, connection )
    if not res['OK']:
      return res
    replicaIDs = []
    for tuple in res['Value']:
      replicaID = tuple[0]
      if not replicaID in replicaIDs:
        replicaIDs.append( replicaID )
    return S_OK( replicaIDs )

  def _getReplicaIDTasks( self, replicaIDs, connection = False ):
    req = "SELECT TaskID FROM TaskReplicas WHERE ReplicaID IN (%s);" % intListToString( replicaIDs )
    res = self._query( req, connection )
    if not res['OK']:
      return res
    taskIDs = []
    for tuple in res['Value']:
      taskID = tuple[0]
      if not taskID in taskIDs:
        taskIDs.append( taskID )
    return S_OK( taskIDs )

  #
  #                               End of monitoring of stage tasks
  #
  ################################################################

  ####################################################################
  #
  # Submission of stage requests
  #

  def setRequest( self, lfnDict, source, callbackMethod, sourceTaskID, connection = False ):
    """ This method populates the StorageManagementDB Tasks table with the requested files. """
    connection = self.__getConnection( connection )
    if not lfnDict:
      return S_ERROR( "No files supplied in request" )
    # The first step is to create the task in the Tasks table
    res = self._createTask( source, callbackMethod, sourceTaskID, connection = connection )
    if not res['OK']:
      return res
    taskID = res['Value']
    # Get the Replicas which already exist in the CacheReplicas table
    allReplicaIDs = []
    taskStates = []
    for se, lfns in lfnDict.items():
      if type( lfns ) in types.StringTypes:
        lfns = [lfns]
      res = self._getExistingReplicas( se, lfns, connection = connection )
      if not res['OK']:
        return res
      existingReplicas = res['Value']
      # Insert the CacheReplicas that do not already exist
      for lfn in lfns:
        if lfn in existingReplicas.keys():
          gLogger.verbose( 'StorageManagementDB.setRequest: Replica already exists in CacheReplicas table %s @ %s' % ( lfn, se ) )
          existingFileState = existingReplicas[lfn][1]
          taskState = self.__getTaskStateFromReplicaState( existingFileState )
          if not taskState in taskStates:
            taskStates.append( taskState )
        else:
          res = self._insertReplicaInformation( lfn, se, 'Stage', connection = connection )
          if not res['OK']:
            self._cleanTask( taskID, connection = connection )
            return res
          else:
            existingReplicas[lfn] = ( res['Value'], 'New' )
      allReplicaIDs.extend( existingReplicas.values() )
    # Insert all the replicas into the TaskReplicas table
    res = self._insertTaskReplicaInformation( taskID, allReplicaIDs, connection = connection )
    if not res['OK']:
      self._cleanTask( taskID, connection = connection )
      return res
    # Check whether the the task status is Done based on the existing file states
    # If all the files for a particular Task are 'Staged', update the Task
    if taskStates == ['Staged']:
    #so if the tasks are for LFNs from the lfns dictionary, which are already staged,
    #they immediately change state New->Done. Fixed it to translate such tasks to 'Staged' state
      self.__updateTaskStatus( [taskID], 'Staged', True, connection = connection )
    if 'Failed' in taskStates:
      self.__updateTaskStatus( [taskID], 'Failed', True, connection = connection )
    return S_OK( taskID )

  def _cleanTask( self, taskID, connection = False ):
    """ Remove a task and any related information """
    connection = self.__getConnection( connection )
    self.removeTasks( [taskID], connection = connection )
    self.removeUnlinkedReplicas( connection = connection )

  def _createTask( self, source, callbackMethod, sourceTaskID, connection = False ):
    """ Enter the task details into the Tasks table """
    connection = self.__getConnection( connection )
    req = "INSERT INTO Tasks (Source,SubmitTime,CallBackMethod,SourceTaskID) VALUES ('%s',UTC_TIMESTAMP(),'%s','%s');" % ( source, callbackMethod, sourceTaskID )
    res = self._update( req, connection )
    if not res['OK']:
      gLogger.error( "StorageManagementDB._createTask: Failed to create task.", res['Message'] )
      return res
    #gLogger.info( "%s_DB:%s" % ('_createTask',req))
    taskID = res['lastRowId']
    reqSelect = "SELECT * FROM Tasks WHERE TaskID = %s;" % ( taskID )
    resSelect = self._query( reqSelect, connection )
    if not resSelect['OK']:
      gLogger.info( "%s.%s_DB: problem retrieving record: %s. %s" % ( self._caller(), '_createTask', reqSelect, resSelect['Message'] ) )
    gLogger.info( "%s.%s_DB: inserted Tasks = %s" % ( self._caller(), '_createTask', resSelect['Value'][0] ) )

    #gLogger.info("StorageManagementDB._createTask: Created task with ('%s','%s','%s') and obtained TaskID %s" % (source,callbackMethod,sourceTaskID,taskID))
    return S_OK( taskID )

  def _getExistingReplicas( self, storageElement, lfns, connection = False ):
    """ Obtains the ReplicasIDs for the replicas already entered in the CacheReplicas table """
    connection = self.__getConnection( connection )
    req = "SELECT ReplicaID,LFN,Status FROM CacheReplicas WHERE SE = '%s' AND LFN IN (%s);" % ( storageElement, stringListToString( lfns ) )
    res = self._query( req, connection )
    if not res['OK']:
      gLogger.error( 'StorageManagementDB._getExistingReplicas: Failed to get existing replicas.', res['Message'] )
      return res
    existingReplicas = {}
    for replicaID, lfn, status in res['Value']:
      existingReplicas[lfn] = ( replicaID, status )
    return S_OK( existingReplicas )

  def _insertReplicaInformation( self, lfn, storageElement, type, connection = False ):
    """ Enter the replica into the CacheReplicas table """
    connection = self.__getConnection( connection )
    req = "INSERT INTO CacheReplicas (Type,SE,LFN,PFN,Size,FileChecksum,GUID,SubmitTime,LastUpdate) VALUES ('%s','%s','%s','',0,'','',UTC_TIMESTAMP(),UTC_TIMESTAMP());" % ( type, storageElement, lfn )
    res = self._update( req, connection )
    if not res['OK']:
      gLogger.error( "_insertReplicaInformation: Failed to insert to CacheReplicas table.", res['Message'] )
      return res
    #gLogger.info( "%s_DB:%s" % ('_insertReplicaInformation',req))

    replicaID = res['lastRowId']
    reqSelect = "SELECT * FROM CacheReplicas WHERE ReplicaID = %s;" % ( replicaID )
    resSelect = self._query( reqSelect, connection )
    if not resSelect['OK']:
      gLogger.info( "%s.%s_DB: problem retrieving record: %s. %s" % ( self._caller(), '_insertReplicaInformation', reqSelect, resSelect['Message'] ) )

    gLogger.info( "%s.%s_DB: inserted CacheReplicas = %s" % ( self._caller(), '_insertReplicaInformation', resSelect['Value'][0] ) )
    #gLogger.verbose("_insertReplicaInformation: Inserted Replica ('%s','%s') and obtained ReplicaID %s" % (lfn,storageElement,replicaID))
    return S_OK( replicaID )

  def _insertTaskReplicaInformation( self, taskID, replicaIDs, connection = False ):
    """ Enter the replicas into TaskReplicas table """
    connection = self.__getConnection( connection )
    req = "INSERT INTO TaskReplicas (TaskID,ReplicaID) VALUES "
    for replicaID, status in replicaIDs:
      replicaString = "(%s,%s)," % ( taskID, replicaID )
      req = "%s %s" % ( req, replicaString )
    req = req.rstrip( ',' )
    res = self._update( req, connection )
    if not res['OK']:
      gLogger.error( 'StorageManagementDB._insertTaskReplicaInformation: Failed to insert to TaskReplicas table.', res['Message'] )
      return res
    #gLogger.info( "%s_DB:%s" % ('_insertTaskReplicaInformation',req))
    gLogger.info( "StorageManagementDB._insertTaskReplicaInformation: Successfully added %s CacheReplicas to Task %s." % ( res['Value'], taskID ) )
    return S_OK()

  #
  #                               End of insertion methods
  #
  ################################################################

  ####################################################################

  def getWaitingReplicas( self, connection = False ):
    connection = self.__getConnection( connection )
    req = "SELECT TR.TaskID, R.Status, COUNT(*) from TaskReplicas as TR, CacheReplicas as R where TR.ReplicaID=R.ReplicaID GROUP BY TR.TaskID,R.Status;"
    res = self._query( req, connection )
    if not res['OK']:
      gLogger.error( 'StorageManagementDB.getWaitingReplicas: Failed to get eligible TaskReplicas', res['Message'] )
      return res
    badTasks = []
    goodTasks = []
    for taskID, status, count in res['Value']:
      if taskID in badTasks:
        continue
      elif status in ( 'New', 'Failed' ):
        badTasks.append( taskID )
      elif status == 'Waiting':
        goodTasks.append( taskID )
    replicas = {}
    if not goodTasks:
      return S_OK( replicas )
    return self.getCacheReplicas( {'Status':'Waiting', 'TaskID':goodTasks}, connection = connection )

  ####################################################################

  def getTasksWithStatus( self, status ):
    """ This method retrieves the TaskID from the Tasks table with the supplied Status. """
    req = "SELECT TaskID,Source,CallBackMethod,SourceTaskID from Tasks WHERE Status = '%s';" % status
    res = self._query( req )
    if not res['OK']:
      return res
    taskIDs = {}
    for taskID, source, callback, sourceTask in res['Value']:
      taskIDs[taskID] = ( source, callback, sourceTask )
    return S_OK( taskIDs )

  ####################################################################
  #
  # The state transition of the CacheReplicas from *->Failed
  #

  def updateReplicaFailure( self, terminalReplicaIDs ):
    """ This method sets the status to Failure with the failure reason for the supplied Replicas. """
    res = self.updateReplicaStatus( terminalReplicaIDs.keys(), 'Failed' )
    if not res['OK']:
      return res
    updated = res['Value']
    if not updated:
      return S_OK( updated )
    for replicaID in updated:
      reqSelect = "Select * FROM CacheReplicas WHERE ReplicaID = %d" % ( replicaID )
      resSelect = self._query( reqSelect )
      if not resSelect['OK']:
        gLogger.info( "%s.%s_DB: problem retrieving record: %s. %s" % ( self._caller(), 'updateReplicaFailure', reqSelect, resSelect['Message'] ) )

      req = "UPDATE CacheReplicas SET Reason = '%s' WHERE ReplicaID = %d" % ( terminalReplicaIDs[replicaID], replicaID )
      res = self._update( req )
      if not res['OK']:
        gLogger.error( 'StorageManagementDB.updateReplicaFailure: Failed to update replica fail reason.', res['Message'] )
        return res

      replicaIDs = []
      for record in resSelect['Value']:
        replicaIDs.append( record[0] )
        gLogger.info( "%s.%s_DB: to_update CacheReplicas =  %s" % ( self._caller(), 'updateReplicaFailure', record ) )

      reqSelect1 = "SELECT * FROM CacheReplicas WHERE ReplicaID IN (%s);" % intListToString( replicaIDs )
      resSelect1 = self._query( reqSelect1, connection )
      if not resSelect1['OK']:
        gLogger.info( "%s.%s_DB: problem retrieving records: %s. %s" % ( self._caller(), 'updateReplicaFailure', reqSelect1, resSelect1['Message'] ) )

      for record in resSelect1['Value']:
        gLogger.info( "%s.%s_DB: updated CacheReplicas = %s" % ( self._caller(), 'updateReplicaFailure', record ) )

    return S_OK( updated )

  ####################################################################
  #
  # The state transition of the CacheReplicas from New->Waiting
  #

  def updateReplicaInformation( self, replicaTuples ):
    """ This method set the replica size information and pfn for the requested storage element.  """
    for replicaID, pfn, size in replicaTuples:
      reqSelect = "SELECT * FROM CacheReplicas WHERE ReplicaID = %s and Status != 'Cancelled';" % ( replicaID )
      resSelect = self._query( reqSelect )
      if not resSelect['OK']:
        gLogger.info( "%s.%s_DB: problem retrieving record: %s. %s" % ( self._caller(), 'updateReplicaInformation', reqSelect, resSelect['Message'] ) )

      req = "UPDATE CacheReplicas SET PFN = '%s', Size = %s, Status = 'Waiting' WHERE ReplicaID = %s and Status != 'Cancelled';" % ( pfn, size, replicaID )
      res = self._update( req )
      if not res['OK']:
        gLogger.error( 'StagerDB.updateReplicaInformation: Failed to insert replica information.', res['Message'] )

      replicaIDs = []
      for record in resSelect['Value']:
        replicaIDs.append( record[0] )
        gLogger.info( "%s.%s_DB: to_update CacheReplicas =  %s" % ( self._caller(), 'updateReplicaInformation', record ) )

      reqSelect1 = "SELECT * FROM CacheReplicas WHERE ReplicaID IN (%s);" % intListToString( replicaIDs )
      resSelect1 = self._query( reqSelect1 )
      if not resSelect1['OK']:
        gLogger.info( "%s.%s_DB: problem retrieving record: %s. %s" % ( self._caller(), 'updateReplicaInformation', reqSelect1, resSelect1['Message'] ) )

      for record in resSelect1['Value']:
        gLogger.info( "%s.%s_DB: updated CacheReplicas = %s" % ( self._caller(), 'updateReplicaInformation', record ) )

      gLogger.debug( 'StagerDB.updateReplicaInformation: Successfully updated CacheReplicas record With Status=Waiting, for ReplicaID= %s' % ( replicaID ) )
    return S_OK()

  ####################################################################
  #
  # The state transition of the CacheReplicas from Waiting->StageSubmitted
  #

  def getSubmittedStagePins( self ):
    # change the query to take into account pin expiry time
    #req = "SELECT SE,COUNT(*),SUM(Size) from CacheReplicas WHERE Status NOT IN ('New','Waiting','Failed') GROUP BY SE;"
    req = "SELECT SE,Count(*),SUM(Size) from CacheReplicas,StageRequests WHERE Status NOT IN ('New','Waiting','Failed') and CacheReplicas.ReplicaID=StageRequests.ReplicaID and PinExpiryTime>Now() GROUP BY SE;"
    res = self._query( req )
    if not res['OK']:
      gLogger.error( 'StorageManagementDB.getSubmittedStagePins: Failed to obtain submitted requests.', res['Message'] )
      return res
    storageRequests = {}
    for storageElement, replicas, totalSize in res['Value']:
      storageRequests[storageElement] = {'Replicas':int( replicas ), 'TotalSize':int( totalSize )}
    return S_OK( storageRequests )

  def insertStageRequest( self, requestDict, pinLifeTime ):
    req = "INSERT INTO StageRequests (ReplicaID,RequestID,StageRequestSubmitTime,PinLength) VALUES "
    for requestID, replicaIDs in requestDict.items():
      for replicaID in replicaIDs:
        replicaString = "(%s,'%s',UTC_TIMESTAMP(),%d)," % ( replicaID, requestID, pinLifeTime )
        req = "%s %s" % ( req, replicaString )
    req = req.rstrip( ',' )
    res = self._update( req )
    if not res['OK']:
      gLogger.error( 'StorageManagementDB.insertStageRequest: Failed to insert to StageRequests table.', res['Message'] )
      return res

    for requestID, replicaIDs in requestDict.items():
      for replicaID in replicaIDs:
        #fix, no individual queries
        reqSelect = "SELECT * FROM StageRequests WHERE ReplicaID = %s AND RequestID = '%s';" % ( replicaID, requestID )
        resSelect = self._query( reqSelect )
        if not resSelect['OK']:
          gLogger.info( "%s.%s_DB: problem retrieving record: %s. %s" % ( self._caller(), 'insertStageRequest', reqSelect, resSelect['Message'] ) )
        gLogger.info( "%s.%s_DB: inserted StageRequests = %s" % ( self._caller(), 'insertStageRequest', resSelect['Value'][0] ) )

    #gLogger.info( "%s_DB: howmany = %s" % ('insertStageRequest',res))

    #gLogger.info( "%s_DB:%s" % ('insertStageRequest',req))
    gLogger.debug( "StorageManagementDB.insertStageRequest: Successfully added %s StageRequests with RequestID %s." % ( res['Value'], requestID ) )
    return S_OK()

  ####################################################################
  #
  # The state transition of the CacheReplicas from StageSubmitted->Staged
  #

  def setStageComplete( self, replicaIDs ):
    # Daniela: FIX wrong PinExpiryTime (84000->86400 seconds = 1 day)

    reqSelect = "SELECT * FROM StageRequests WHERE ReplicaID IN (%s);" % intListToString( replicaIDs )
    resSelect = self._query( reqSelect )
    if not resSelect['OK']:
      gLogger.info( "%s.%s_DB: problem retrieving record: %s. %s" % ( self._caller(), 'setStageComplete', reqSelect, resSelect['Message'] ) )

    req = "UPDATE StageRequests SET StageStatus='Staged',StageRequestCompletedTime = UTC_TIMESTAMP(),PinExpiryTime = DATE_ADD(UTC_TIMESTAMP(),INTERVAL 86400 SECOND) WHERE ReplicaID IN (%s);" % intListToString( replicaIDs )
    res = self._update( req )
    if not res['OK']:
      gLogger.error( "StorageManagementDB.setStageComplete: Failed to set StageRequest completed.", res['Message'] )
      return res

    for record in resSelect['Value']:
      gLogger.info( "%s.%s_DB: to_update StageRequests =  %s" % ( self._caller(), 'setStageComplete', record ) )

    reqSelect1 = "SELECT * FROM StageRequests WHERE ReplicaID IN (%s);" % intListToString( replicaIDs )
    resSelect1 = self._query( reqSelect1 )
    if not resSelect1['OK']:
      gLogger.info( "%s.%s_DB: problem retrieving record: %s. %s" % ( self._caller(), 'setStageComplete', reqSelect1, resSelect1['Message'] ) )

    for record in resSelect1['Value']:
      gLogger.info( "%s.%s_DB: updated StageRequests = %s" % ( self._caller(), 'setStageComplete', record ) )

    gLogger.debug( "StorageManagementDB.setStageComplete: Successfully updated %s StageRequests table with StageStatus=Staged for ReplicaIDs: %s." % ( res['Value'], replicaIDs ) )
    return res

  ####################################################################
  #
  # This code handles the finalization of stage tasks
  #
  # Daniela: useless method
  '''
  def updateStageCompletingTasks(self):
    """ This will select all the Tasks in StageCompleting status and check whether all the associated files are Staged. """
    req = "SELECT TR.TaskID,COUNT(if(R.Status NOT IN ('Staged'),1,NULL)) FROM Tasks AS T, TaskReplicas AS TR, CacheReplicas AS R WHERE T.Status='StageCompleting' AND T.TaskID=TR.TaskID AND TR.ReplicaID=R.ReplicaID GROUP BY TR.TaskID;"
    res = self._query(req)
    if not res['OK']:
      return res
    taskIDs = []
    for taskID,count in res['Value']:
      if int(count) == 0:
        taskIDs.append(taskID)
    if not taskIDs:
      return S_OK(taskIDs)
    req = "UPDATE Tasks SET Status = 'Staged' WHERE TaskID IN (%s);" % intListToString(taskIDs)
    res = self._update(req)
    if not res['OK']:
      return res
    return S_OK(taskIDs)
  '''
  def setTasksDone( self, taskIDs ):
    """ This will update the status for a list of taskIDs to Done. """
    reqSelect = "SELECT * FROM Tasks WHERE TaskID IN (%s);" % intListToString( taskIDs )
    resSelect = self._query( reqSelect )
    if not resSelect['OK']:
      gLogger.error( "%s.%s_DB: problem retrieving record: %s. %s" % ( self._caller(), 'setTasksDone', reqSelect, resSelect['Message'] ) )

    req = "UPDATE Tasks SET Status = 'Done', CompleteTime = UTC_TIMESTAMP() WHERE TaskID IN (%s);" % intListToString( taskIDs )
    res = self._update( req )
    if not res['OK']:
      gLogger.error( "StorageManagementDB.setTasksDone: Failed to set Tasks status to Done.", res['Message'] )
      return res

    for record in resSelect['Value']:
      gLogger.info( "%s.%s_DB: to_update Tasks =  %s" % ( self._caller(), 'setTasksDone', record ) )
      #fix, no individual queries
    reqSelect1 = "SELECT * FROM Tasks WHERE TaskID IN (%s);" % intListToString( taskIDs )
    resSelect1 = self._query( reqSelect1, connection )
    if not resSelect1['OK']:
      gLogger.info( "%s.%s_DB: problem retrieving record: %s. %s" % ( self._caller(), 'setTasksDone', reqSelect1, resSelect1['Message'] ) )

    for record in resSelect1['Value']:
      gLogger.info( "%s.%s_DB: updated Tasks = %s" % ( self._caller(), 'setTasksDone', record ) )

    gLogger.debug( "StorageManagementDB.setTasksDone: Successfully updated %s Tasks with StageStatus=Done for taskIDs: %s." % ( res['Value'], taskIDs ) )
    return res

  def removeTasks( self, taskIDs, connection = False ):
    """ This will delete the entries from the TaskReplicas for the provided taskIDs. """
    connection = self.__getConnection( connection )
    req = "DELETE FROM TaskReplicas WHERE TaskID IN (%s);" % intListToString( taskIDs )
    res = self._update( req, connection )
    if not res['OK']:
      gLogger.error( "StorageManagementDB.removeTasks. Problem removing entries from TaskReplicas." )
      return res
    #gLogger.info( "%s_DB:%s" % ('removeTasks',req))
    reqSelect = "SELECT * FROM Tasks WHERE TaskID IN (%s);" % intListToString( taskIDs )
    resSelect = self._query( reqSelect )
    if not resSelect['OK']:
      gLogger.error( "%s.%s_DB: problem retrieving record: %s. %s" % ( self._caller(), 'removeTasks', reqSelect, resSelect['Message'] ) )

    for record in resSelect['Value']:
      gLogger.info( "%s.%s_DB: to_delete Tasks =  %s" % ( self._caller(), 'removeTasks', record ) )

    req = "DELETE FROM Tasks WHERE TaskID in (%s);" % intListToString( taskIDs )
    res = self._update( req, connection )
    if not res['OK']:
       gLogger.error( "StorageManagementDB.removeTasks. Problem removing entries from Tasks." )
    gLogger.info( "%s.%s_DB: deleted Tasks" % ( self._caller(), 'removeTasks' ) )
    #gLogger.info( "%s_DB:%s" % ('removeTasks',req))
    return res

  def removeUnlinkedReplicas( self, connection = False ):
    """ This will remove from the CacheReplicas tables where there are no associated links. """
    connection = self.__getConnection( connection )
    req = "SELECT ReplicaID from CacheReplicas WHERE Links = 0;"
    res = self._query( req, connection )
    if not res['OK']:
      gLogger.error( "StorageManagementDB.removeUnlinkedReplicas. Problem selecting entries from CacheReplicas where Links = 0." )
      return res
    replicaIDs = []
    for tuple in res['Value']:
      replicaIDs.append( tuple[0] )
    if not replicaIDs:
      return S_OK()


    reqSelect = "SELECT * FROM StageRequests WHERE ReplicaID IN (%s);" % intListToString( replicaIDs )
    resSelect = self._query( reqSelect )
    if not resSelect['OK']:
      gLogger.info( "%s.%s_DB: problem retrieving record: %s. %s" % ( self._caller(), 'removeUnlinkedReplicas', reqSelect, resSelect['Message'] ) )
    for record in resSelect['Value']:
      gLogger.info( "%s.%s_DB: to_delete StageRequests = %s" % ( self._caller(), 'removeUnlinkedReplicas', record ) )

    req = "DELETE FROM StageRequests WHERE ReplicaID IN (%s);" % intListToString( replicaIDs )
    res = self._update( req, connection )
    if not res['OK']:
      gLogger.error( "StorageManagementDB.removeUnlinkedReplicas. Problem deleting from StageRequests." )
      return res
    gLogger.info( "%s.%s_DB: deleted StageRequests" % ( self._caller(), 'removeUnlinkedReplicas' ) )

    gLogger.debug( "StorageManagementDB.removeUnlinkedReplicas: Successfully removed %s StageRequests entries for ReplicaIDs: %s." % ( res['Value'], replicaIDs ) )

    reqSelect = "SELECT * FROM CacheReplicas WHERE ReplicaID IN (%s);" % intListToString( replicaIDs )
    resSelect = self._query( reqSelect )
    if not resSelect['OK']:
      gLogger.info( "%s.%s_DB: problem retrieving record: %s. %s" % ( self._caller(), 'removeUnlinkedReplicas', reqSelect, resSelect['Message'] ) )
    for record in resSelect['Value']:
      gLogger.info( "%s.%s_DB: to_delete CacheReplicas =  %s" % ( self._caller(), 'removeUnlinkedReplicas', record ) )

    req = "DELETE FROM CacheReplicas WHERE ReplicaID IN (%s);" % intListToString( replicaIDs )
    res = self._update( req, connection )
    if res['OK']:
      gLogger.info( "%s.%s_DB: deleted CacheReplicas" % ( self._caller(), 'removeUnlinkedReplicas' ) )
      gLogger.debug( "StorageManagementDB.removeUnlinkedReplicas: Successfully removed %s CacheReplicas entries for ReplicaIDs: %s." % ( res['Value'], replicaIDs ) )
    else:
      gLogger.error( "StorageManagementDB.removeUnlinkedReplicas. Problem removing entries from CacheReplicas." )
    return res
