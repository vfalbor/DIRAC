# $HeadURL$
__RCSID__ = "$Id$"

import urllib2, re, tarfile, os

from DIRAC import gLogger, S_OK, S_ERROR
from DIRAC.Core.Utilities import CFG, File

def getRepositoryVersions( package = False, isCMTCompatible = False ):
  if package:
    webLocation = 'http://svnweb.cern.ch/guest/dirac/%s/tags/%s' % ( package, package )
  else:
    webLocation = 'http://svnweb.cern.ch/guest/dirac/tags'
    package = "global release"
  try:
    remoteFile = urllib2.urlopen( webLocation )
  except urllib2.URLError:
    gLogger.exception()
    sys.exit( 2 )
  remoteData = remoteFile.read()
  remoteFile.close()
  if not remoteData:
    gLogger.error( "Could not retrieve versions for package %s" % package )
    sys.exit( 1 )
  versions = []
  if isCMTCompatible and package:
    rePackage = "%s_.*" % package
  else:
    rePackage = ".*"
  versionRE = re.compile( "<li> *<a *href=.*> *(%s)/ *</a> *</li>" % rePackage )
  for line in remoteData.split( "\n" ):
    res = versionRE.search( line )
    if res:
      versions.append( res.groups()[0] )
  return versions

def loadCFGFromRepository( svnPath ):
  import urllib2, stat
  gLogger.info( "Reading %s" % ( svnPath ) )
  if svnPath[0] == "/":
    svnPath = svnPath[1:]
  viewSVNLocation = "http://svnweb.cern.ch/world/wsvn/dirac/%s?op=dl&rev=0" % ( svnPath )
  anonymousLocation = 'http://svnweb.cern.ch/guest/dirac/%s' % ( svnPath )
  for remoteLocation in ( anonymousLocation, viewSVNLocation ):
    try:
      remoteFile = urllib2.urlopen( remoteLocation )
    except urllib2.URLError:
      gLogger.exception()
      continue
    remoteData = remoteFile.read()
    remoteFile.close()
    if remoteData:
      return CFG.CFG().loadFromBuffer( remoteData )
  #Web cat failed. Try directly with svn
  exitStatus, remoteData = execAndGetOutput( "svn cat 'http://svnweb.cern.ch/guest/dirac/%s'" % ( svnPath ) )
  if exitStatus:
    print "Error: Could not retrieve %s from the web nor via SVN. Aborting..." % svnPath
    sys.exit( 1 )
  return CFG.CFG().loadFromBuffer( remoteData )

def createTarball( tarballPath, directoryToTar ):
  tf = tarfile.open( tarballPath, "w:gz" )
  tf.add( directoryToTar, os.path.basename( directoryToTar ), recursive = True )
  tf.close()
  md5FilePath = False
  for suffix in ( ".tar.gz", ".gz" ):
    sLen = len( suffix )
    if tarballPath[ len( tarballPath ) - sLen: ] == suffix:
      md5FilePath = "%s.md5" % tarballPath[:-sLen]
      break
  if not md5FilePath:
    return S_ERROR( "Could not generate md5 filename" )
  md5str = File.getMD5ForFiles( [ tarballPath ] )
  fd = open( md5FilePath, "w" )
  fd.write( md5str )
  fd.close()
  return S_OK()
