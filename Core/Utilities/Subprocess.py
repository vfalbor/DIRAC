# $HeadURL$
"""
   DIRAC Wrapper to execute python and system commands with a wrapper, that might
   set a timeout.
   3 FUNCTIONS are provided:
     - shellCall( iTimeOut, cmdSeq, callbackFunction = None, env = None ):
       it uses subprocess.Popen class with "shell = True".
       If cmdSeq is a string, it specifies the command string to execute through
       the shell.  If cmdSeq is a sequence, the first item specifies the command
       string, and any additional items will be treated as additional shell arguments.

     - systemCall( iTimeOut, cmdSeq, callbackFunction = None, env = None ):
       it uses subprocess.Popen class with "shell = False".
       cmdSeq should be a string, or a sequence of program arguments.

       stderr and stdout are piped. callbackFunction( pipeId, line ) can be
       defined to process the stdout (pipeId = 0) and stderr (pipeId = 1) as
       they are produced

       They return a DIRAC.ReturnValue dictionary with a tuple in Value
       ( returncode, stdout, stderr ) the tuple will also be available upon
       timeout error or buffer overflow error.

     - pythonCall( iTimeOut, function, *stArgs, **stKeyArgs )
       calls function with given arguments within a timeout Wrapper
       should be used to wrap third party python functions
"""
__RCSID__ = "$Id$"

# Very Important:
#  Here we can not import directly from DIRAC, since this file it is imported
#  at initialization time therefore the full path is necessary
# from DIRAC import S_OK, S_ERROR
from DIRAC.Core.Utilities.ReturnValues import S_OK, S_ERROR
# from DIRAC import gLogger
from DIRAC.FrameworkSystem.Client.Logger import gLogger
from DIRAC.Core.Utilities import DEncode

import time
import select
import os
import sys
import types
import subprocess
import signal

class Subprocess:

  def __init__( self, timeout = False, bufferLimit = 52428800 ):
    self.log = gLogger.getSubLogger( 'Subprocess' )
    self.timeout = False
    try:
      self.changeTimeout( timeout )
      self.bufferLimit = int( bufferLimit ) # 5MB limit for data
    except Exception, x:
      self.log.exception( 'Failed initialisation of Subprocess object' )
      raise x
    self.child = None
    self.childPID = 0
    self.childKilled = False
    self.callback = None
    self.bufferList = []
    self.cmdSeq = []

  def changeTimeout( self, timeout ):
    self.timeout = int( timeout )
    if self.timeout == 0:
      self.timeout = False
    self.log.debug( 'Timeout set to', timeout )

  def __readFromFD( self, fd, baseLength = 0 ):
    dataString = ''
    redBuf = " "

    while len( redBuf ) > 0:
      redBuf = os.read( fd, 8192 )
      dataString += redBuf
      if len( dataString ) + baseLength > self.bufferLimit:
        self.log.error( 'Maximum output buffer length reached' )
        retDict = S_ERROR( 'Reached maximum allowed length (%d bytes) '
                           'for called function return value' % self.bufferLimit )
        retDict[ 'Value' ] = dataString
        return retDict

    return S_OK( dataString )

  def __executePythonFunction( self, function, writePipe, *stArgs, **stKeyArgs ):
    try:
      os.write( writePipe, DEncode.encode( S_OK( function( *stArgs, **stKeyArgs ) ) ) )
    except OSError, x:
      if str( x ) == '[Errno 32] Broken pipe':
        # the parent has died
        pass
    except Exception, x:
      self.log.exception( 'Exception while executing', function.__name__ )
      os.write( writePipe, DEncode.encode( S_ERROR( str( x ) ) ) )
      #HACK: Allow some time to flush logs
      time.sleep( 1 )
    try:
      os.close( writePipe )
    finally:
      os._exit( 0 )

  def __selectFD( self, readSeq, timeout = False ):
    validList = []
    for fd in readSeq:
      try:
        os.fstat( fd )
        validList.append( fd )
      except OSError:
        pass
    if not validList:
      return False
    if self.timeout and not timeout:
      timeout = self.timeout
    if not timeout:
      return select.select( validList , [], [] )[0]
    else:
      return select.select( validList , [], [], timeout )[0]

  def __killPid( self, pid, sig = 9 ):
    try:
      os.kill( pid, sig )
    except Exception, x:
      if not str( x ) == '[Errno 3] No such process':
        self.log.exception( 'Exception while killing timed out process' )
        raise x

  def __poll( self, pid ):
    try:
      return os.waitpid( pid, os.WNOHANG )
    except os.error:
      if self.childKilled:
        return False
      return None

  def killChild( self, recursive = True ):
    if self.childPID < 1:
      self.log.error( "Could not kill child. Child PID is %s" % self.childPID )
      return - 1
    os.kill( self.childPID, signal.SIGSTOP )
    if recursive:
      for gcpid in getChildrenPIDs( self.childPID, lambda cpid: os.kill( cpid, signal.SIGSTOP ) ):
        try:
          os.kill( gcpid, signal.SIGKILL )
          self.__poll( gcpid )
        except Exception:
          pass
    self.__killPid( self.childPID )

    #HACK to avoid python bug
    # self.child.wait()
    exitStatus = self.__poll( self.childPID )
    i = 0
    while exitStatus == None and i < 1000:
      i += 1
      time.sleep( 0.000001 )
      exitStatus = self.__poll( self.childPID )
    try:
      exitStatus = os.waitpid( self.childPID, 0 )
    except os.error:
      pass
    self.childKilled = True
    if exitStatus == None:
      return exitStatus
    return exitStatus[1]

  def pythonCall( self, function, *stArgs, **stKeyArgs ):
    readFD, writeFD = os.pipe()
    pid = os.fork()
    self.childPID = pid
    if pid == 0:
      os.close( readFD )
      self.__executePythonFunction( function, writeFD, *stArgs, **stKeyArgs )
      # FIXME: the close it is done at __executePythonFunction, do we need it here?
      os.close( writeFD )
    else:
      os.close( writeFD )
      readSeq = self.__selectFD( [ readFD ] )
      if readSeq == False:
        return S_ERROR( "Can't read from call %s" % ( function.__name__ ) )
      try:
        if len( readSeq ) == 0:
          self.log.debug( 'Timeout limit reached for pythonCall', function.__name__ )
          self.__killPid( pid )

          #HACK to avoid python bug
          # self.wait()
          retries = 10000
          while os.waitpid( pid, 0 ) == -1 and retries > 0:
            time.sleep( 0.001 )
            retries -= 1

          return S_ERROR( '%d seconds timeout for "%s" call' % ( self.timeout, function.__name__ ) )
        elif readSeq[0] == readFD:
          retDict = self.__readFromFD( readFD )
          os.waitpid( pid, 0 )
          if retDict[ 'OK' ]:
            dataStub = retDict[ 'Value' ]
            if not dataStub:
              return S_ERROR( "Error decoding data coming from call" )
            retObj, stubLen = DEncode.decode( dataStub )
            if stubLen == len( dataStub ):
              return retObj
            else:
              return S_ERROR( "Error decoding data coming from call" )
          return retDict
      finally:
        os.close( readFD )

  def __generateSystemCommandError( self, exitStatus, message ):
    retDict = S_ERROR( message )
    retDict[ 'Value' ] = ( exitStatus,
                           self.bufferList[0][0],
                           self.bufferList[1][0] )
    return retDict

  def __readFromFile( self, fd, baseLength, doAll = True ):
    try:
      dataString = ""
      fn = fd.fileno()
      rawRead = type( fn ) == types.IntType
      while fd in select.select( [ fd ], [], [], 1 )[0]:
        if rawRead:
          nB = os.read( fn, self.bufferLimit )
        else:
          nB = fd.read( 1 )
        if nB == "":
          break
        dataString += nB
    except Exception, x:
      self.log.exception( "SUPROCESS: readFromFile exception" )
      try:
        self.log.error( 'Error reading', 'type(nB) =%s' % type( nB ) )
        self.log.error( 'Error reading', 'nB =%s' % str( nB ) )
      except Exception:
        pass
      return S_ERROR( 'Can not read from output: %s' % str( x ) )
    if len( dataString ) + baseLength > self.bufferLimit:
      self.log.error( 'Maximum output buffer length reached' )
      retDict = S_ERROR( 'Reached maximum allowed length (%d bytes) for called '
                         'function return value' % self.bufferLimit )
      retDict[ 'Value' ] = dataString
      return retDict

    return S_OK( dataString )

  def __readFromSystemCommandOutput( self, fd, bufferIndex ):
    retDict = self.__readFromFile( fd,
                                   len( self.bufferList[ bufferIndex ][0] ) )
    if retDict[ 'OK' ]:
      self.bufferList[ bufferIndex ][0] += retDict[ 'Value' ]
      if not self.callback == None:
        while self.__callLineCallback( bufferIndex ):
          pass
      return S_OK()
    else: # buffer size limit reached killing process (see comment on __readFromFile)
      exitStatus = self.killChild()

      return self.__generateSystemCommandError( 
                  exitStatus,
                  "%s for '%s' call" % ( retDict['Message'], self.cmdSeq ) )

  def systemCall( self, cmdSeq, callbackFunction = None, shell = False, env = None ):
    self.cmdSeq = cmdSeq
    self.callback = callbackFunction
    if sys.platform.find( "win" ) == 0:
      closefd = False
    else:
      closefd = True
    try:
      self.child = subprocess.Popen( self.cmdSeq,
                                      shell = shell,
                                      stdout = subprocess.PIPE,
                                      stderr = subprocess.PIPE,
                                      close_fds = closefd,
                                      env = env )
      self.childPID = self.child.pid
    except OSError, v:
      retDict = S_ERROR( v )
      retDict['Value'] = ( -1, '' , str( v ) )
      return retDict
    except Exception, x:
      try:
        self.child.stdout.close()
        self.child.stderr.close()
      except Exception:
        pass
      retDict = S_ERROR( v )
      retDict['Value'] = ( -1, '' , str( x ) )
      return retDict

    try:
      self.bufferList = [ [ "", 0 ], [ "", 0 ] ]
      initialTime = time.time()

      exitStatus = self.__poll( self.child.pid )

      while ( 0, 0 ) == exitStatus or None == exitStatus:
        retDict = self.__readFromCommand()
        if not retDict[ 'OK' ]:
          return retDict

        if self.timeout and time.time() - initialTime > self.timeout:
          exitStatus = self.killChild()
          self.__readFromCommand()
          return self.__generateSystemCommandError( 
                      exitStatus,
                      "Timeout (%d seconds) for '%s' call" %
                      ( self.timeout, cmdSeq ) )
        time.sleep( 0.01 )
        exitStatus = self.__poll( self.child.pid )

      self.__readFromCommand()

      if exitStatus:
        exitStatus = exitStatus[1]

      if exitStatus >= 256:
        exitStatus /= 256
      return S_OK( ( exitStatus, self.bufferList[0][0], self.bufferList[1][0] ) )
    finally:
      try:
        self.child.stdout.close()
        self.child.stderr.close()
      except Exception:
        pass

  def getChildPID( self ):
    return self.childPID

  def __readFromCommand( self, isLast = False ):
    fdList = []
    for i in ( self.child.stdout, self.child.stderr ):
      try:
        if not i.closed:
          fdList.append( i.fileno() )
      except Exception:
        self.log.exception( "SUBPROCESS: readFromCommand exception" )
    readSeq = self.__selectFD( fdList, True )
    if readSeq == False:
      return S_OK()
    if self.child.stdout.fileno() in readSeq:
      retDict = self.__readFromSystemCommandOutput( self.child.stdout, 0 )
      if not retDict[ 'OK' ]:
        return retDict
    if self.child.stderr.fileno() in readSeq:
      retDict = self.__readFromSystemCommandOutput( self.child.stderr, 1 )
      if not retDict[ 'OK' ]:
        return retDict
    return S_OK()

  def __callLineCallback( self, bufferIndex ):
    nextLineIndex = self.bufferList[ bufferIndex ][0][ self.bufferList[ bufferIndex ][1]: ].find( "\n" )
    if nextLineIndex > -1:
      try:
        self.callback( bufferIndex, self.bufferList[ bufferIndex ][0][
                        self.bufferList[ bufferIndex ][1]:
                        self.bufferList[ bufferIndex ][1] + nextLineIndex ] )
        #Each line processed is taken out of the buffer to prevent the limit from killing us
        nL = self.bufferList[ bufferIndex ][1] + nextLineIndex + 1
        self.bufferList[ bufferIndex ][0] = self.bufferList[ bufferIndex ][0][ nL: ]
        self.bufferList[ bufferIndex ][1] = 0
      except Exception:
        self.log.exception( 'Exception while calling callback function',
                           '%s' % self.callback.__name__ )
        self.log.showStack()

      return True
    return False

def systemCall( timeout, cmdSeq, callbackFunction = None, env = None, bufferLimit = 52428800 ):
  """
     Use SubprocessExecutor class to execute cmdSeq (it can be a string or a sequence)
     with a timeout wrapper, it is executed directly without calling a shell
  """
  spObject = Subprocess( timeout, bufferLimit = bufferLimit )
  return spObject.systemCall( cmdSeq,
                              callbackFunction = callbackFunction,
                              env = env,
                              shell = False )

def shellCall( timeout, cmdSeq, callbackFunction = None, env = None, bufferLimit = 52428800 ):
  """
     Use SubprocessExecutor class to execute cmdSeq (it can be a string or a sequence)
     with a timeout wrapper, cmdSeq it is invoque by /bin/sh
  """
  spObject = Subprocess( timeout, bufferLimit = bufferLimit )
  return spObject.systemCall( cmdSeq,
                              callbackFunction = callbackFunction,
                              env = env,
                              shell = True )

def pythonCall( timeout, function, *stArgs, **stKeyArgs ):
  """
     Use SubprocessExecutor class to execute function with provided arguments,
     with a timeout wrapper.
  """
  spObject = Subprocess( timeout )
  return spObject.pythonCall( function, *stArgs, **stKeyArgs )

def __getChildrenForPID( ppid ):
  """
  Get a list of children pids for ppid
  """
  magicCmd = "ps --no-headers --ppid %d -o pid" % ppid
  try:
    import psutil
    childrenList = []
    for proc in psutil.process_iter():
      if proc.ppid == ppid:
        childrenList.append( proc.pid )
    return childrenList
  except Exception:
    exc = subprocess.Popen( magicCmd,
                            stdout = subprocess.PIPE,
                            shell = True,
                            close_fds = True )
    exc.wait()
    return [ int( pid.strip() ) for pid in exc.stdout.readlines() if pid.strip() ]


def getChildrenPIDs( ppid, foreachFunc = None ):
  """
  Get all children recursively for a given ppid.
   Optional foreachFunc will be executed for each children pid
  """
  cpids = __getChildrenForPID( ppid )
  pids = []
  for pid in cpids:
    pids.append( pid )
    if foreachFunc:
      foreachFunc( pid )
    pids.extend( getChildrenPIDs( pid, foreachFunc ) )
  return pids
