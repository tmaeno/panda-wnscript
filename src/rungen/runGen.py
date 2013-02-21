#!/bin/bash

"exec" "python" "-u" "$0" "$@"

import os
import re
import sys
import time
import urllib
import getopt
import pickle
import commands
import threading
import xml.dom.minidom

# error code
EC_MissingArg  = 10
EC_NoInput     = 11
EC_DBRelease   = 144
EC_WGET        = 146
EC_LFC         = 147

print "=== start ==="
print time.ctime()

debugFlag    = False
libraries    = ''
outputFiles  = {}
jobParams    = ''
inputFiles   = []
inputGUIDs   = []
oldPrefix    = ''
newPrefix    = ''
directIn     = False
usePFCTurl   = False
lfcHost      = ''
givenPFN     = False
envvarFile   = ''
liveLog      = ''
sourceURL    = 'https://gridui07.usatlas.bnl.gov:25443'
inMap        = {}
archiveJobO  = ''
useAthenaPackages = False
dbrFile      = ''
dbrRun       = -1
notExpandDBR = False
skipInputByRetry = []
writeInputToTxt = ''
rootVer   = ''
useRootCore = False
useMana   = False

# command-line parameters
opts, args = getopt.getopt(sys.argv[1:], "i:o:r:j:l:p:u:a:",
                           ["pilotpars","debug","oldPrefix=","newPrefix=",
                            "directIn","sourceURL=","lfcHost=","envvarFile=",
			    "inputGUIDs=","liveLog=","inMap=",
                            "useAthenaPackages",
                            "dbrFile=","dbrRun=","notExpandDBR",
                            "useFileStager", "usePFCTurl", "accessmode=",
                            "skipInputByRetry=","writeInputToTxt=",
			    "rootVer=","enable-jem","jem-config=",
                            "mergeOutput","mergeType=","mergeScript=",
			    "useRootCore","givenPFN","useMana"
                            ])
for o, a in opts:
    if o == "-l":
        libraries=a
    if o == "-j":
        scriptName=a
    if o == "-r":
        runDir=a
    if o == "-p":
        jobParams=urllib.unquote(a)
    if o == "-i":
        exec "inputFiles="+a
    if o == "-o":
        exec "outputFiles="+a
    if o == "--debug":
        debugFlag = True
    if o == "--inputGUIDs":
        exec "inputGUIDs="+a
    if o == "--oldPrefix":
        oldPrefix = a
    if o == "--newPrefix":
        newPrefix = a
    if o == "--directIn":
        directIn = True
    if o == "--lfcHost":
        lfcHost = a
    if o == "--liveLog":
        liveLog = a
    if o == "--sourceURL":
        sourceURL = a
    if o == "--inMap":
        exec "inMap="+a
    if o == "-a":
        archiveJobO = a
    if o == "--useAthenaPackages":
        useAthenaPackages = True
    if o == "--dbrFile":
        dbrFile = a
    if o == "--dbrRun":
        dbrRun = a
    if o == "--notExpandDBR":
        notExpandDBR = True
    if o == "--usePFCTurl":
        usePFCTurl = True
    if o == "--skipInputByRetry":
        skipInputByRetry = a.split(',')
    if o == "--writeInputToTxt":
        writeInputToTxt = a
    if o == "--rootVer":
        rootVer = a 
    if o == "--useRootCore":
        useRootCore = True
    if o == "--givenPFN":
        givenPFN = True
    if o == "--useMana":
        useMana = True

# dump parameter
try:
    print "=== parameters ==="
    print libraries
    print runDir
    print jobParams
    print inputFiles
    print scriptName
    print outputFiles
    print inputGUIDs
    print oldPrefix
    print newPrefix
    print directIn
    print usePFCTurl
    print lfcHost
    print debugFlag
    print liveLog
    print sourceURL
    print inMap
    print useAthenaPackages
    print archiveJobO
    print dbrFile
    print dbrRun
    print notExpandDBR
    print "skipInputByRetry",skipInputByRetry
    print "writeInputToTxt",writeInputToTxt
    print "rootVer",rootVer
    print "useRootCore",useRootCore
    print "givenPFN",givenPFN
    print "useMana",useMana
    print "==================="
except:
    type, value, traceBack = sys.exc_info()
    print 'ERROR: missing parameters : %s - %s' % (type,value)
    sys.exit(EC_MissingArg)

# remove skipped files
if skipInputByRetry != []: 
    tmpInputList = []
    for tmpLFN in inputFiles:
        if not tmpLFN in skipInputByRetry:
            tmpInputList.append(tmpLFN)
    inputFiles = tmpInputList
    print "removed skipped files -> %s"% str(inputFiles)

# log watcher
class LogWatcher (threading.Thread):
    # onstructor
    def __init__(self,fileName,logName):
        threading.Thread.__init__(self)
        self.fileName = fileName
        self.logName  = logName
        self.offset   = 0
        self.lock     = threading.Lock()

    # terminate thread
    def terminate(self):
        self.lock.acquire()

    # main
    def run(self):
        print "start LogWatcher"
        while True:
            try:
                import zlib
                import socket
                import httplib
                import mimetools
                # read log
                logFH = open(self.fileName)
                logFH.seek(self.offset)
                logStr = logFH.read()
                logFH.close()
                # upload
                if len(logStr) != 0:
                    # compress
                    zStr = zlib.compress(logStr)
                    # construct HTTP request
                    boundary = mimetools.choose_boundary()
                    body  = '--%s\r\n' % boundary
                    body += 'Content-Disposition: form-data; name="file"; filename="%s"\r\n' % self.logName
                    body += 'Content-Type: application/octet-stream\r\n'
                    body += '\r\n' + zStr + '\r\n'
                    body += '--%s--\r\n\r\n' % boundary
                    headers = {'Content-Type': 'multipart/form-data; boundary=%s' % boundary,
                               'Content-Length': str(len(body))}
                    url = '%s/server/panda/updateLog' % sourceURL
                    match = re.search('[^:/]+://([^/]+)(/.+)',url)
                    host = match.group(1)
                    path = match.group(2)
                    # set timeout
                    socket.setdefaulttimeout(60)
                    # HTTPS connection
                    conn = httplib.HTTPSConnection(host)
                    conn.request('POST',path,body,headers)
                    resp = conn.getresponse()
                    data = resp.read()
                    conn.close()
                    print "updated LogWatcher at %s" % time.strftime('%Y-%m-%d %H:%M:%S',time.gmtime())
            except:
                type, value, traceBack = sys.exc_info()
                print 'failed to update LogWatcher %s - %s' % (type,value)
            # check lock
            if self.lock.acquire(0):
                self.lock.release()
                time.sleep(60)
            else:
                # terminate
		print "terminate LogWatcher"
                return


# get PFNs from LRC
def _getPFNsFromLRC (urlLRC,items,isGUID=True,old_prefix='',new_prefix=''):
    # old prefix for regex
    old_prefix_re = old_prefix.replace('?','\?')
    pfnMap = {}
    if len(items)>0:
        # get PoolFileCatalog
        iITEM = 0
        strITEMs = ''
        for item in items:
            iITEM += 1
            # make argument
            strITEMs += '%s ' % item
            if iITEM % 35 == 0 or iITEM == len(items):
                # get PoolFileCatalog
                strITEMs = strITEMs.rstrip()
                if isGUID:
                    data = {'guids':strITEMs}
                else:
                    data = {'lfns':strITEMs}                    
                # avoid too long argument
                strITEMs = ''
                # GET
                url = '%s/lrc/PoolFileCatalog?%s' % (urlLRC,urllib.urlencode(data))
                req = urllib2.Request(url)
                fd = urllib2.urlopen(req)
                out = fd.read()
                if out.startswith('Error'):
                    continue
                if not out.startswith('<?xml'):
                    continue
                # get SURLs
                try:
                    root  = xml.dom.minidom.parseString(out)
                    files = root.getElementsByTagName('File')
                    for file in files:
                        # get ID
                        id = str(file.getAttribute('ID'))
                        # get PFN node
                        physical = file.getElementsByTagName('physical')[0]
                        pfnNode  = physical.getElementsByTagName('pfn')[0]
                        # convert UTF8 to Raw
                        pfn = str(pfnNode.getAttribute('name'))
                        # remove :8443/srm/managerv1?SFN=
                        pfn = re.sub(':8443/srm/managerv1\?SFN=','',pfn)
                        if old_prefix=='':
                            # remove protocol and host
                            pfn = re.sub('^[^:]+://[^/]+','',pfn)
                            # remove redundant /
                            pfn = re.sub('^//','/',pfn)
                            # put dcache if /pnfs
                            if pfn.startswith('/pnfs'):
                                pfn = 'dcache:%s' % pfn
                        else:
                            # check matching
                            if re.search(old_prefix_re,pfn) == None:
                                continue
                            # replace prefix
                            pfn = re.sub(old_prefix_re,new_prefix,pfn)
                        # append
                        pfnMap[id] = pfn
                except:
                    pass
    return pfnMap

# get PFNs from LFC
lfcCommand = """
import os
import re
import sys
import time
import pickle

# get PFNs from LFC
def _getPFNsFromLFC (lfc_host,items,old_prefix='',new_prefix=''):
    retVal = 0 
    pfnMap = {}
    # old prefix for regex
    old_prefix_re = old_prefix.replace('?','\?')
    # import lfc
    try:
        import lfc
    except:
        print "ERROR : cound not import lfc"
        retVal = 1
        return retVal,pfnMap
    # set LFC HOST
    os.environ['LFC_HOST'] = lfc_host
    # check bulk-operation
    if not hasattr(lfc,'lfc_getreplicas'):
        print "ERROR : bulk-ops is unsupported"
        retVal = 2        
        return retVal,pfnMap
    frList = []
    # set nGUID for bulk-ops
    nGUID = 100
    iGUID = 0
    mapLFN = {}
    listGUID = []
    # loop over all items
    for item in items:
        iGUID += 1
        listGUID.append(item)
        if iGUID % nGUID == 0 or iGUID == len(items):
            # get replica
            nTry = 5
            for iTry in range(nTry):
                ret,resList = lfc.lfc_getreplicas(listGUID,'')
                if ret == 0 or iTry+1 == nTry:
                    break
                print "sleep due to LFC error"
                time.sleep(60)
            if ret != 0:
                err_num = lfc.cvar.serrno
                err_string = lfc.sstrerror(err_num)
                print "ERROR : LFC access failure - %s" % err_string
            else:
                for fr in resList:
                    if fr != None and ((not hasattr(fr,'errcode')) or \
                                       (hasattr(fr,'errcode') and fr.errcode == 0)):
                        print "replica found for %s" % fr.guid
                        # skip empty or corrupted SFN 
                        print fr.sfn      
                        if fr.sfn == '' or re.search('[^\w\./\-\+\?:&=]',fr.sfn) != None:
                            if globalVerbose:
                                print "WARNING : wrong SFN '%s'" % fr.sfn
                            continue
                        # check matching
                        if old_prefix != '':
                            if re.search(old_prefix_re,fr.sfn) == None:
                                continue
                        guid = fr.guid
                        # use first one
                        if pfnMap.has_key(guid):
                            onDiskFlag = False
                            for diskPath in ['/MCDISK/','/BNLT0D1/','/atlasmcdisk/','/atlasdatadisk/']:
                                if re.search(diskPath,fr.sfn) != None:
                                    onDiskFlag = True
                                    break
                            if not onDiskFlag:
                                continue
                            print "use disk replica"  
                        if old_prefix == '':
                            # remove protocol and host
                            pfn = re.sub('[^:]+://[^/]+','',fr.sfn)
                            pfn = new_prefix + pfn
                        else:
                            pfn = re.sub(old_prefix_re,new_prefix,fr.sfn) 
                        # assign
                        pfnMap[guid] = pfn
            # reset                        
            listGUID = []
    # return        
    return retVal,pfnMap
"""

# collect GUIDs from PoolFileCatalog
directTmpTurl = {}
try:
    print "===== PFC from pilot ====="
    tmpPcFile = open("PoolFileCatalog.xml")
    print tmpPcFile.read()
    tmpPcFile.close()
    # parse XML
    root  = xml.dom.minidom.parse("PoolFileCatalog.xml")
    files = root.getElementsByTagName('File')
    for file in files:
        # get ID
        id = str(file.getAttribute('ID'))
        # get PFN node
        physical = file.getElementsByTagName('physical')[0]
        pfnNode  = physical.getElementsByTagName('pfn')[0]
        # convert UTF8 to Raw
        pfn = str(pfnNode.getAttribute('name'))
        lfn = pfn.split('/')[-1]
        # append
        directTmpTurl[id] = pfn
except:
    type, value, traceBack = sys.exc_info()
    print 'ERROR : Failed to collect GUIDs : %s - %s' % (type,value)

# scan LFC/LRC for direct reading
if directIn and not givenPFN:
    if usePFCTurl:
        # Use the TURLs from PoolFileCatalog.xml created by pilot
        print "===== GUIDs and TURLs in PFC ====="
        print directTmpTurl
        directTmp = directTmpTurl
    else:
        if lfcHost != '':
            # get PFNs from LFC
            lfcPy = '%s/%s.py' % (os.getcwd(),commands.getoutput('uuidgen 2>/dev/null'))
            lfcOutPi = '%s/lfc.%s' % (os.getcwd(),commands.getoutput('uuidgen 2>/dev/null'))
            lfcPyFile = open(lfcPy,'w')
            lfcPyFile.write(lfcCommand+("""
st,out= _getPFNsFromLFC ('%s',%s,old_prefix='%s',new_prefix='%s')
outPickFile = open('%s','w')
pickle.dump(out,outPickFile)
outPickFile.close()
sys.exit(st)
    """ % (lfcHost,inputGUIDs,oldPrefix,newPrefix,lfcOutPi)))
            lfcPyFile.close()
            # run LFC access in grid runtime
            lfcSh = '%s.sh' % commands.getoutput('uuidgen 2>/dev/null')
            if envvarFile != '':
                commands.getoutput('cat %s > %s' % (envvarFile,lfcSh))
            # check LFC module
            foundGoodPython = False
            print "->check LFC.py with python" 
            lfcS,lfcO = commands.getstatusoutput('python -c "import lfc"')
            print lfcS
            if lfcS == 0:
                commands.getoutput('echo "python %s" >> %s' % (lfcPy,lfcSh))
                foundGoodPython = True
            if not foundGoodPython:
                if os.environ.has_key('ATLAS_PYTHON_PILOT'):
                    print "->check LFC.py with $ATLAS_PYTHON_PILOT=%s" % os.environ['ATLAS_PYTHON_PILOT']
                    lfcS,lfcO = commands.getstatusoutput('%s -c "import lfc"' % os.environ['ATLAS_PYTHON_PILOT'])
                    print lfcS
                    if lfcS == 0:
                        commands.getoutput('echo "%s %s" >> %s' % (os.environ['ATLAS_PYTHON_PILOT'],lfcPy,lfcSh))
                        foundGoodPython= True
            if not foundGoodPython:            
                # use system python
                print "->use /usr/bin/python"
                commands.getoutput('echo "/usr/bin/python %s" >> %s' % (lfcPy,lfcSh))
            commands.getoutput('chmod +x %s' % lfcSh)
            tmpSt,tmpOut = commands.getstatusoutput('./%s' % lfcSh)
            print tmpSt
            print tmpOut
            # error check
            if re.search('ERROR : LFC access failure',tmpOut) != None:
                sys.exit(EC_LFC)
            if tmpSt == 0:
                lfcOutPiFile = open(lfcOutPi)
                directTmp = pickle.load(lfcOutPiFile)
                lfcOutPiFile.close()            
            else:
                directTmp = {}
        else:
            # get PFNs from LRC    
            directTmp = _getPFNsFromLRC (urlLRC,inputFiles+minbiasFiles+cavernFiles,
                                         isGUID=False,old_prefix=oldPrefix,
                                         new_prefix=newPrefix)
    # collect LFNs
    directPFNs = {}
    for id in directTmp.keys():
        lfn = directTmp[id].split('/')[-1]
	lfn = re.sub('__DQ2-\d+$','',lfn)
        directPFNs[lfn] = directTmp[id]

# save current dir
currentDir = os.getcwd()
currentDirFiles = os.listdir('.')
print "Running in",currentDir

# crate work dir
workDir = currentDir+"/workDir"
commands.getoutput('rm -rf %s' % workDir)
os.makedirs(workDir)
os.chdir(workDir)

# expand libraries
if libraries == '':
    pass
elif libraries.startswith('/'):
    print commands.getoutput('tar xvfzm %s' % libraries)
else:
    print commands.getoutput('tar xvfzm %s/%s' % (currentDir,libraries))

# expand jobOs if needed
if archiveJobO != "" and (useAthenaPackages or libraries == ''):
    print "--- wget for jobO ---"
    output = commands.getoutput('wget -h')
    wgetCommand = 'wget'
    for line in output.split('\n'):
        if re.search('--no-check-certificate',line) != None:
            wgetCommand = 'wget --no-check-certificate'
            break
    com = '%s %s/cache/%s' % (wgetCommand,sourceURL,archiveJobO)
    nTry = 3
    for iTry in range(nTry):
        print 'Try : %s' % iTry
        status,output = commands.getstatusoutput(com)
        print output
        if status == 0:
            break
        if iTry+1 == nTry:
            print "ERROR : cound not get jobO files from panda server"
            sys.exit(EC_WGET)
        time.sleep(30)    
    print commands.getoutput('tar xvfzm %s' % archiveJobO)

# create cmt dir to setup Athena
setupEnv = ''
if useAthenaPackages:
    tmpDir = '%s/%s/cmt' % (workDir,commands.getoutput('uuidgen 2>/dev/null'))
    print "Making tmpDir",tmpDir
    os.makedirs(tmpDir)
    # create requirements
    oFile = open(tmpDir+'/requirements','w')
    oFile.write('use AtlasPolicy AtlasPolicy-*\n')
    oFile.close()
    # setup command
    setupEnv  = 'export CMTPATH=%s:$CMTPATH; ' % workDir
    setupEnv += 'cd %s; cmt config; source ./setup.sh; cd -; ' % tmpDir
# setup root
if rootVer != '':
    rootBinDir = workDir + '/pandaRootBin'
    # use CVMFS if setup script is available
    if os.path.exists('%s/pandaUseCvmfSetup.sh' % rootBinDir):
        iFile = open('%s/pandaUseCvmfSetup.sh' % rootBinDir)
        setupEnv += iFile.read()
        iFile.close()
        setupEnv += ' root.exe -q;'
    else:
        setupEnv += ' export ROOTSYS=%s/root; export PATH=$ROOTSYS/bin:$PATH; export LD_LIBRARY_PATH=$ROOTSYS/lib:$LD_LIBRARY_PATH; export PYTHONPATH=$ROOTSYS/lib:$PYTHONPATH; root.exe -q; ' % rootBinDir
# RootCore
if useRootCore:
    pandaRootCoreWD = os.path.abspath(runDir+'/__panda_rootCoreWorkDir')
    setupEnv += 'source %s/RootCore/scripts/grid_run.sh %s; ' % (pandaRootCoreWD,pandaRootCoreWD) 

# mana
if useMana:
    setupEnv += "export ATLAS_LOCAL_ROOT_BASE=/cvmfs/atlas.cern.ch/repo/ATLASLocalRootBase; "
    setupEnv += "source $ATLAS_LOCAL_ROOT_BASE/user/atlasLocalSetup.sh --quiet; "
    setupEnv += "source $ATLAS_LOCAL_ROOT_BASE/packageSetups/atlasLocalManaSetup.sh --manaVersion ${manaVersionVal}; "
    setupEnv += "cd %s; hwaf asetup mana;  hwaf configure; cd %s; " % (workDir,runDir)

# TestArea
setupEnv += "export TestArea=%s; " % workDir

# Tracer On
try:
    from pandawnutil.tracer import RunTracer
    rTracer = RunTracer.RunTracer()
    rTracer.make()
    setupEnv += rTracer.getEnvVar()
except:
    pass

# make rundir just in case
commands.getoutput('mkdir %s' % runDir)
# go to run dir
os.chdir(runDir)

# check input files
if inputFiles != [] and not givenPFN:
    print "=== check input files ==="
    newInputs = []
    inputFileMap = {}
    for inputFile in inputFiles:
        # direct reading
        foundFlag = False
        if directIn:
            if directPFNs.has_key(inputFile):
                newInputs.append(directPFNs[inputFile])
                foundFlag = True
                inputFileMap[inputFile] = directPFNs[inputFile]
        else:
            # make symlinks to input files
            if inputFile in currentDirFiles:
                os.symlink('%s/%s' % (currentDir,inputFile),inputFile)
                newInputs.append(inputFile)
                foundFlag = True
                inputFileMap[inputFile] = inputFile
        if not foundFlag:
            print "%s not exist" % inputFile
    inputFiles = newInputs
    if len(inputFiles) == 0:
        print "ERROR : No input file is available"
        sys.exit(EC_NoInput)        
    print "=== New inputFiles ==="
    print inputFiles
            

# setup DB/CDRelease
dbrSetupStr = ''
if dbrFile != '':
    if notExpandDBR:
        # just make a symlink
        print commands.getstatusoutput('ln -fs %s/%s %s' % (currentDir,dbrFile,dbrFile))
    else:
        if dbrRun == -1:
            print "=== setup DB/CDRelease (old style) ==="
            # expand 
            status,out = commands.getstatusoutput('tar xvfzm %s/%s' % (currentDir,dbrFile))
            print out
            # remove
            print commands.getstatusoutput('rm %s/%s' % (currentDir,dbrFile))
        else:
            print "=== setup DB/CDRelease (new style) ==="
            # make symlink
            print commands.getstatusoutput('ln -fs %s/%s %s' % (currentDir,dbrFile,dbrFile))
            # run Reco_trf and set env vars
            dbCom = 'Reco_trf.py RunNumber=%s DBRelease=%s' % (dbrRun,dbrFile)
            print dbCom
            status,out = commands.getstatusoutput(dbCom)
            print out
            # remove
            print commands.getstatusoutput('rm %s/%s' % (currentDir,dbrFile))
        # look for setup.py
        tmpSetupDir = None
        for line in out.split('\n'):
            if line.endswith('setup.py'):
                tmpSetupDir = re.sub('setup.py$','',line)
                break
        # check
        if tmpSetupDir == None:
            print "ERROR : could not find setup.py in %s" % dbrFile
            sys.exit(EC_DBRelease)
        # run setup.py
        dbrSetupStr  = "import os\nos.chdir('%s')\nexecfile('setup.py',{})\nos.chdir('%s')\n" % \
                       (tmpSetupDir,os.getcwd())
        dbrSetupStr += "import sys\nsys.stdout.flush()\nsys.stderr.flush()\n"

            
# add current dir to PATH
os.environ['PATH'] = '.:'+os.environ['PATH']

print "=== env variables ==="
if dbrFile != '' and dbrSetupStr != '':
    # change env by DBR
    tmpTrfName = 'trf.%s.py' % commands.getoutput('uuidgen 2>/dev/null')
    tmpTrfFile = open(tmpTrfName,'w')
    tmpTrfFile.write(dbrSetupStr)
    tmpTrfFile.write('import sys\nstatus=os.system("""env""")\n')
    tmpTrfFile.close()
    print commands.getoutput(setupEnv+'python -u '+tmpTrfName)
else:
    print commands.getoutput(setupEnv+'env')
print

# put ROOT.py to avoid a crash caused by long argument at direct access site
commands.getoutput('rm ROOT.py')
rootFile = open('ROOT.py','w')
rootFile.write("""
print 'INFO: trying to wrap ROOT.py'
import os    
import sys
import copy
origPath = copy.copy(sys.path)
origArgv = copy.copy(sys.argv)
sys.path = sys.path[1:]
try:
    sys.path.remove('')
except:
    pass
try:
    sys.path.remove('.')
except:
    pass
try:
    sys.path.remove(os.getcwd())
except:
    pass
sys.argv[1:]=[]
import ROOT
reload(ROOT)
from ROOT import *
sys.path = origPath
sys.argv = origArgv
try:
    print 'INFO: using %s' % sys.modules['ROOT']
    print 'INFO: ROOT.py has been successfully wrapped'
except:
    print 'ERROR: failed to wrap ROOT.py'
""")
rootFile.close()               


print "=== ls %s ===" % runDir
print commands.getoutput('ls -l')
print

# chmod +x just in case
commands.getoutput('chmod +x %s' % scriptName)
if scriptName == '':
    commands.getoutput('chmod +x %s' % jobParams.split()[0])

# replace input files
newJobParams = jobParams
if inputFiles != []:
    # decompose to stream and filename
    writeInputToTxtMap = {}
    if writeInputToTxt != '':
	for tmpItem in writeInputToTxt.split(','):
            tmpItems = tmpItem.split(':')
            if len(tmpItems) == 2:
                tmpStream,tmpFileName = tmpItems
                writeInputToTxtMap[tmpStream] = tmpFileName
    if writeInputToTxtMap != {}:
        print "=== write input to file ==="
    if inMap == {}:
        inStr = ''
        for inputFile in inputFiles:
            inStr += "%s," % inputFile
        inStr = inStr[:-1]
        # replace
        newJobParams = newJobParams.replace('%IN',inStr)
        # write to file
        tmpKeyName = 'IN'
        if writeInputToTxtMap.has_key(tmpKeyName):
            commands.getoutput('rm -f %s' % writeInputToTxtMap[tmpKeyName])
            tmpInFile = open(writeInputToTxtMap[tmpKeyName],'w')
            tmpInFile.write(inStr)
            tmpInFile.close()
            print "%s to %s : %s" % (tmpKeyName,writeInputToTxtMap[tmpKeyName],inStr)
    else:
        # multiple inputs
        for tmpToken,tmpList in inMap.iteritems():
            inStr = ''
            for inputFile in tmpList:
                if inputFileMap.has_key(inputFile):
                    inStr += "%s," % inputFileMap[inputFile]
            inStr = inStr[:-1] + ' '
            # replace
	    newJobParams = re.sub('%'+tmpToken+'(?P<sname> |$|\"|\')',inStr+'\g<sname>',newJobParams)
            # write to file
            tmpKeyName = tmpToken
            if writeInputToTxtMap.has_key(tmpKeyName):
                commands.getoutput('rm -f %s' % writeInputToTxtMap[tmpKeyName])
                tmpInFile = open(writeInputToTxtMap[tmpKeyName],'w')
                tmpInFile.write(inStr)
                tmpInFile.close()
                print "%s to %s : %s" % (tmpKeyName,writeInputToTxtMap[tmpKeyName],inStr)
    if writeInputToTxtMap != {}:
        print 
                
# construct command
com = setupEnv
tmpTrfName = 'trf.%s.py' % commands.getoutput('uuidgen 2>/dev/null')
tmpTrfFile = open(tmpTrfName,'w')
if dbrFile != '' and dbrSetupStr != '':
    tmpTrfFile.write(dbrSetupStr)
# wrap commands to invoke execve even if preload is removed/changed
tmpTrfFile.write('import os,sys\nstatus=os.system(r"""%s %s""")\n' % (scriptName,newJobParams))
tmpTrfFile.write('status %= 255\nsys.exit(status)\n\n')
tmpTrfFile.close()
com += 'cat %s;python -u %s' % (tmpTrfName,tmpTrfName)

# temporary output to avoid MemeoryError
tmpOutput = 'tmp.stdout.%s' % commands.getoutput('uuidgen 2>/dev/null')
tmpStderr = 'tmp.stderr.%s' % commands.getoutput('uuidgen 2>/dev/null')


print "=== execute ==="
print com
# run athena
if not debugFlag:
    # write stdout to tmp file
    com += ' > %s 2> %s' % (tmpOutput,tmpStderr)
    status,out = commands.getstatusoutput(com)
    print out
    status %= 255
    try:
        tmpOutFile = open(tmpOutput)
        for line in tmpOutFile:
            print line[:-1]
        tmpOutFile.close()
    except:
        pass
    try:
        stderrSection = True
        tmpErrFile = open(tmpStderr)
        for line in tmpErrFile:
            if stderrSection:
                stderrSection = False
                print "\n=== stderr ==="
            print line[:-1]
        tmpErrFile.close()
    except:
        pass
    # print 'sh: line 1:  8278 Aborted'
    try:
        if status != 0:
            print out.split('\n')[-1]
    except:
        pass
else:
    status = os.system(com)

print
print "=== ls %s ===" % runDir
print commands.getoutput('ls -l')
print

# rename output files
for oldName,newName in outputFiles.iteritems():
    if oldName.find('*') != -1:
        # archive *
        print commands.getoutput('tar cvfz %s %s' % (newName,oldName))
    else:
        print commands.getoutput('mv %s %s' % (oldName,newName))
    # modify PoolFC.xml
    pfcName = 'PoolFileCatalog.xml'
    pfcSt,pfcOut = commands.getstatusoutput('ls %s' % pfcName)
    if pfcSt == 0:
        try:
            pLines = ''
            pFile = open(pfcName)
            for line in pFile:
                # replace file name
                line = re.sub('"%s"' % oldName, '"%s"' % newName, line)
                pLines += line
            pFile.close()
            # overwrite
            pFile = open(pfcName,'w')
            pFile.write(pLines)
            pFile.close()
        except:
            pass


# copy results
for file in outputFiles.values():
    commands.getoutput('mv %s %s' % (file,currentDir))


# create empty PoolFileCatalog.xml if it doesn't exist
pfcName = 'PoolFileCatalog.xml'
pfcSt,pfcOut = commands.getstatusoutput('ls %s' % pfcName)
if pfcSt != 0:
    pfcFile = open(pfcName,'w')
    pfcFile.write("""<?xml version="1.0" encoding="UTF-8" standalone="no" ?>
<!-- Edited By POOL -->
<!DOCTYPE POOLFILECATALOG SYSTEM "InMemory">
<POOLFILECATALOG>

</POOLFILECATALOG>
""")
    pfcFile.close()

# copy PFC
commands.getoutput('mv %s %s' % (pfcName,currentDir))

# copy tracer log
commands.getoutput('mv %s %s' % (rTracer.getLogName(),currentDir))

# go back to current dir
os.chdir(currentDir)

print
print commands.getoutput('pwd')
print commands.getoutput('ls -l')

# remove work dir
if not debugFlag:
    commands.getoutput('rm -rf %s' % workDir)

# return
if status:
    print "execute script: Running script failed : StatusCode=%d" % status
    sys.exit(status)
else:
    print "execute script: Running script was successful"
    sys.exit(0)
