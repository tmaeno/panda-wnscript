#!/usr/bin/env python

import re
import sys
import os
import os.path
import getopt
import commands
import shutil
import tarfile
import xml.dom.minidom
import traceback
import pickle
import urllib

## error codes
EC_OK = 0

## error codes implementing https://twiki.cern.ch/twiki/bin/viewauth/Atlas/PandaErrorCodes
EC_MissingArg           = 126         # the argument to this script is not given properly
EC_NoInput              = 141         # input file access problem (e.g. file is missing or unaccessible from WN)
EC_LFC                  = EC_NoInput  # it uses only for direct I/O which is not enabled for the moment
EC_IFILE_UNAVAILABLE    = EC_NoInput  # cannot access any of the input files
EC_OFILE_UNAVAILABLE    = 102         # merged file (the output) is not produced
EC_MERGE_SCRIPTNOFOUND  = 80          # merging script cannot be found on WN
EC_MERGE_ERROR          = 85          # catch-all for non-zero code returned from the underlying merging command 

## error codes not recognized yet by Panda
EC_ITYPE_UNSUPPORTED    = 81          # unsupported merging type

## supported file types for merging
SUPP_TYPES = ['hist','ntuple','pool','user', 'log', 'text']

def __usage__():
    '''
    Run Merge

    Usage:

    $ source $SITEROOT/setup.sh
    $ source $T_DISTREL/AtlasRelease/*/cmt/setup.sh -tag_add=???
    
    '''

    sys.stdout.write(__usage__.__doc__ + '\n')

def urisplit(uri):
   """
   Basic URI Parser according to STD66 aka RFC3986

   >>> urisplit("scheme://authority/path?query#fragment")
   ('scheme', 'authority', 'path', 'query', 'fragment')

   """
   # regex straight from STD 66 section B
   regex = '^(([^:/?#]+):)?(//([^/?#]*))?([^?#]*)(\?([^#]*))?(#(.*))?'
   p = re.match(regex, uri).groups()
   scheme, authority, path, query, fragment = p[1], p[3], p[4], p[6], p[8]
   #if not path: path = None
   return (scheme, authority, path, query, fragment)

def __exec__(cmd, mergelog=False):
    '''
    wrapper of making system call
    '''
    print 'dir : %s' % os.getcwd()
    print 'exec: %s' % cmd
    s,o = commands.getstatusoutput(cmd)
    print 'status: %s' % (s % 255)
    print 'stdout:\n%s' % o
    return s,o

def __resolvePoolFileCatalog__(PFC='PoolFileCatalog.xml'):
    '''
    resolving the PoolFileCatalog.xml file produced by the pilot job
    '''
    # collect GUIDs from PoolFileCatalog
    turls = {}
    try:
        print "===== PFC from pilot ====="
        tmpPcFile = open(PFC)
        print tmpPcFile.read()
        tmpPcFile.close()
        # parse XML
        root  = xml.dom.minidom.parse(PFC)
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
            turls[id] = pfn
    except:
        type, value, traceBack = sys.exc_info()
        print 'ERROR : Failed to collect GUIDs : %s - %s' % (type,value)

    return turls

def __getPFNsFromLRC__(urlLRC,items,isGUID=True,old_prefix='',new_prefix=''):
    '''
    resolving PFNs from LRC
    '''

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

def __getPFNsFromLFC__(lfcHost, items, envvarFile='', old_prefix='', new_prefix=''):
    '''
    resolving PFNs from LFC
    '''

    pfnMap = {}

    # get PFNs from LFC
    lfcPy = '%s/%s.py' % (os.getcwd(),commands.getoutput('uuidgen 2>/dev/null'))
    lfcOutPi = '%s/lfc.%s' % (os.getcwd(),commands.getoutput('uuidgen 2>/dev/null'))
    lfcPyFile = open(lfcPy,'w')

    lfcPyFile.write(__code_getPFNsFromLFC__() + ("""
st,out= _getPFNsFromLFC ('%s',%s,old_prefix='%s',new_prefix='%s')
outPickFile = open('%s','w')
pickle.dump(out,outPickFile)
outPickFile.close()
sys.exit(st)
""" % (lfcHost,items,old_prefix,new_prefix,lfcOutPi)))

    lfcPyFile.close()
    
    # run LFC access in grid runtime
    lfcSh = '%s.sh' % commands.getoutput('uuidgen 2>/dev/null')
    if envvarFile != '':
        commands.getoutput('cat %s > %s' % (envvarFile,lfcSh))
        
    # check LFC module in grid runtime
    print "->check LFC.py"
    lfcS,lfcO = __exec__('python -c "import lfc"')
    print lfcS
    #print lfcO
    if lfcS == 0:
        commands.getoutput('echo "python %s" >> %s' % (lfcPy,lfcSh))
    else:
        # use system python
        print "->use /usr/bin/python"
        commands.getoutput('echo "/usr/bin/python %s" >> %s' % (lfcPy,lfcSh))
        
    commands.getoutput('chmod +x %s' % lfcSh)
    tmpSt,tmpOut = __exec__('./%s' % lfcSh)
    print tmpSt
    print tmpOut
    # error check
    if re.search('ERROR : LFC access failure',tmpOut) != None:
        sys.exit(EC_LFC)
        
    if tmpSt == 0:
        lfcOutPiFile = open(lfcOutPi)
        pfnMap = pickle.load(lfcOutPiFile)
        lfcOutPiFile.close()

    return pfnMap

def __code_getPFNsFromLFC__():
    '''
    generating python function for resolving PFNs from LFC
    
    PS: Not sure why it cannot be a normal python function in this code ... just copied from runAthena
    '''

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
    return lfcCommand

def __cmd_setup_env__(workDir, rootVer):

    # create cmt dir to setup Athena
    setupEnv = ''

    if useAthenaPackages:
        tmpDir = '%s/%s/cmt' % (workDir,commands.getoutput('uuidgen 2>/dev/null'))
        print "Making tmpDir",tmpDir
        os.makedirs(tmpDir)
        # create requirements
        oFile = open(tmpDir+'/requirements','w')
        oFile.write('use AtlasPolicy AtlasPolicy-*\n')
        oFile.write('use PathResolver PathResolver-* Tools\n')
        oFile.close()
        # setup command
        setupEnv  = 'export CMTPATH=%s:$CMTPATH; ' % workDir
        setupEnv += 'cd %s; cat requirements; cmt config; source ./setup.sh; cd -; ' % tmpDir


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
        if os.path.exists('%s/RootCore/scripts/grid_run.sh' % pandaRootCoreWD):
            setupEnv += 'source %s/RootCore/scripts/grid_run.sh %s; ' % (pandaRootCoreWD,pandaRootCoreWD) 

    # TestArea
    setupEnv += "export TestArea=%s; " % workDir

    print "=== setup command ==="
    print setupEnv
    print
    print "=== env ==="
    print commands.getoutput(setupEnv+'env')

    return setupEnv

def __fetch_toolbox__(url, maxRetry=3):
    '''
    getting the runMerge toolbox containing executables, librarys to run merging programs
    '''
    print '=== getting sandbox ==='
    ick = False

    cmd = 'wget --no-check-certificate -t %d --waitretry=60 %s' % (maxRetry, url)
    rc, output = __exec__(cmd)

    if rc == 0:
        ick = True
    else:
        print 'ERROR: wget %s error: %s' % (url, output)
    print
    return ick

def __cat_file__(fpath):
    '''
    print the text content of given fpath to stdout
    '''

    print '=== cat %s ===' % fpath

    if os.path.exists(fpath):

        f = open(fpath,'r')

        for l in map( lambda x:x.strip(), f.readlines()):
            print l

        f.close()

def __merge_root__(inputFiles, outputFile, cmdEnvSetup='', useFileStager=False):
    '''
    merging files with hmerge
    '''

    EC = 0

    print 'merging with hmerge ...'

    ftools = ['hmerge','fs_copy']

    for f in ftools:
        __exec__('cp %s/%s .; chmod +x %s' % (currentDir, f, f))

    cmd  = cmdEnvSetup

    cmd += ' export PATH=.:$PATH;'
    cmd += ' hmerge -f'
    
    if useFileStager:
        cmd += ' -t'

        ## TODO: detect local protocol on demand
        protocol = 'lcgcp'

        cmd += ' -p %s' % protocol

    cmd += ' -o %s' % outputFile
    cmd += ' %s'    % ' '.join(inputFiles)

    rc, output = __exec__(cmd, mergelog=True)

    if rc != 0:
        print "ERROR: hmerge returns error code %d" % rc
        EC = EC_MERGE_ERROR

    return EC

def __merge_tgz__(inputFiles, outputFile, cmdEnvSetup, useFileStager=False):
    '''
    merging (tgzed) files into a tgz tarball
    '''

    EC = 0

    print 'merging with tgz ...'

    o_tgz = None

    f_log = open("merge_job.log","w")

    try:
        o_tgz = tarfile.open(outputFile, mode='w:gz')

        f_idx = 0

        ## regex for extracting panda jobsetID and subjob seqID
        re_ext = re.compile('.*\.([0-9]+\.\_[0-9]+)\..*')

        for fname in inputFiles:

            ## the fname in local directory can be a symbolic link, look to the original fpath instead
            fpath = os.path.realpath( fname )

            ## try to resolve the panda jobsetID and subjob seqID
            f_ext = repr(f_idx)
            f_idx += 1
            f = re_ext.search( fname )
            if f:
                f_ext =  f.group(1)

            if tarfile.is_tarfile(fpath):
                f = tarfile.open(fpath, mode='r:gz')

                for tarinfo in f.getmembers():
                    if not tarinfo.issym():
                        ## alter tarinfo member name to avoid same file name
                        ## in different input tarfiles 
                        ## act only on files in the first directory level
                        if not tarinfo.isdir() and tarinfo.name.find('/') < 0:
                            l_tarinfo = tarinfo.name.split('.')
                            l_tarinfo.insert(-1, f_ext)
                            tarinfo.name = '.'.join(l_tarinfo)

                        o_tgz.addfile(tarinfo, f.extractfile(tarinfo))
                    else:
                        f_log.write('%s:skip symlink %s ==> %s\n' % (fname, tarinfo.name, tarinfo.linkname))
            else:
                f = open(fpath,'r')
                tarinfo = o_tgz.gettarinfo(arcname=fname, fileobj=f)
                o_tgz.addfile(tarinfo, f)

            f.close()

        o_tgz.close()

        if os.path.exists( outputFile ) and tarfile.is_tarfile( outputFile ):
            f_log.write('=== content of merged tarfile ===\n')
            for m in tarfile.open(outputFile, 'r').getmembers():
                f_log.write('%s\n' % m.name)
        else:
            print "ERROR: tarfile %s not created properly" % outputFile
            EC = EC_MERGE_ERROR

    except Exception:
        traceback.print_exc(limit=None, file=f_log)
        EC = EC_MERGE_ERROR
    else:
        ## try to close opened files
        try:
            f_log.close()
        except:
            pass

        try: 
            o_tgz.close() 
        except: 
            pass

    return EC

def __merge_trf__(inputFiles, outputFile, cmdEnvSetup, useFileStager=False):
    '''
    merging files with functions provided by PATJobTransforms
    '''

    EC = 0

    print 'merging with Merging_trf.py from PATJobTransforms ...'

    cmd = cmdEnvSetup + ' get_files -scripts Merging_trf.py'
    rc, output = __exec__(cmd)

    if rc != 0:
        print output
        EC = EC_MERGE_SCRIPTNOFOUND

    else:

        pre_inc_path = os.path.join( currentDir , 'merge_trf_pre.py' )

        cmd  = cmdEnvSetup
        cmd += ' export PATH=.:$PATH;'
        cmd += ' Merging_trf.py preInclude=\'%s\' inputAODFile=\'%s\'' % ( pre_inc_path, ','.join(inputFiles))
        cmd += ' outputAODFile=\'%s\'' % outputFile

        if dbrFile:
            ## make symbolic link of the dbrFile
            __exec__('ln -fs %s/%s %s' % (currentDir,dbrFile,dbrFile))
            cmd += ' DBRelease=\'%s\'' % dbrFile

        cmd += ' autoConfiguration=everything'

        rc,output = __exec__(cmd, mergelog=True)

        if rc != 0:
            print "ERROR: Merging_trf returns error code %d" % rc
            EC = EC_MERGE_ERROR

    return EC

def __merge_user__(inputFiles, outputFile, cmdEnvSetup, userCmd, useFileStager=False):
    '''
    merging files using user provided script
    '''

    EC = 0

    userCmd_new = ''

    ## backward compatible with old --mergeScript
    ## which assumes the script takes -o as output option and the rest of arguments as input filenames
    if len( userCmd.split() ) == 1:
        userCmd_new = '%s -o %s %s' % (userCmd, outputFile, ' '.join(inputFiles))
    else:
        userCmd_new = __replace_IN_OUT_arguments__( userCmd, inputFiles, outputFile )

    print 'merging with user command %s ...' % userCmd_new

    cmd  = cmdEnvSetup;

    cmd += ' export PATH=.:$PATH;'
    cmd += ' %s' % userCmd_new

    rc, output = __exec__(cmd, mergelog=True)

    if rc != 0:
        print "ERROR: user merging command %s returns error code %d" % (userCmd_new, rc)
        EC = EC_MERGE_ERROR

    return EC

def __run_merge__(inputType, inputFiles, outputFile, cmdEnvSetup='', userCmd=None, useFileStager=False):
    '''
    all-in-one function to run different type of merging algorithms
    '''

    EC = 0

    if inputType in ['hist','ntuple']:
        EC = __merge_root__(inputFiles, outputFile, cmdEnvSetup, useFileStager)

    elif inputType in ['pool']:
        EC = __merge_trf__(inputFiles, outputFile, cmdEnvSetup, useFileStager)

    elif inputType in ['log', 'text']:
        EC = __merge_tgz__(inputFiles, outputFile, cmdEnvSetup, useFileStager)

    elif inputType in ['user']:
        if userCmd:
            EC = __merge_user__(inputFiles, outputFile, cmdEnvSetup, userCmd, useFileStager)
        else:
            EC = EC_MERGE_SCRIPTNOFOUND
    else:
        EC = EC_ITYPE_UNSUPPORTED

    return EC

def __replace_IN_OUT_arguments__(arg_str, inputFiles, outputFile):
    '''
    replace %IN and %OUT withh proper values
    '''

    arg_str_new = arg_str.replace('%IN', '"%s"' % (','.join( inputFiles )) ).replace( '%OUT', '"%s"' % outputFile )
    
    return arg_str_new


def __getMergeType__(inputList,mergeScript):
    '''
    get merge type
    '''
    baseFile = inputList[0]
    # log
    if re.search('log\.tgz(\.\d+)*$',baseFile) != None:
        return 'log'
    # user defined
    if mergeScript != '':
        return 'user'
    # pool
    if re.search('pool\.root(\.\d+)*$',baseFile) != None:
        return 'pool'
    # root
    if re.search('.root(\.\d+)*$',baseFile) != None:
        return 'ntuple'
    # others
    return 'text'


if __name__ == "__main__":

    '''
    Main program starts from here
    '''

    ## default values copied from runGen
    debugFlag    = False
    libraries    = ''
    #outputFiles  = {}
    jobParams    = ''
    mexec        = ''
    inputFiles   = []
    inputGUIDs   = []
    oldPrefix    = ''
    newPrefix    = ''
    directIn     = False
    usePFCTurl   = False
    lfcHost      = ''
    envvarFile   = ''
    liveLog      = ''
    sourceURL    = 'https://gridui07.usatlas.bnl.gov:25443'
    inMap        = {}
    archiveJobO  = ''
    useAthenaPackages = False
    dbrFile      = ''
    dbrRun       = -1
    notExpandDBR = False
    useFileStager = False
    skipInputByRetry = []
    writeInputToTxt = ''
    rootVer   = ''
    runDir    = '.'
    mexec     = ''
    useRootCore = False

    ## default values introduced in runMerge
    inputType  = 'ntuple'
    outputFile = ''
    inputList  = ''
    libTgz     = ''
    parentDS   = ''
    parentContainer = ''
    outputDS   = ''

    # command-line argument parsing
    opts = None
    args = None

    print sys.argv

    try:
        opts, args = getopt.getopt(sys.argv[1:], "i:o:r:j:l:p:u:a:t:f:",
                                   ["pilotpars","debug","oldPrefix=","newPrefix=",
                                    "directIn","sourceURL=","lfcHost=","envvarFile=",
                                    "inputGUIDs=","liveLog=","inMap=",
                                    "libTgz=","outDS=","parentDS=","parentContainer=",
                                    "useAthenaPackages", "useRootCore",
                                    "dbrFile=","dbrRun=","notExpandDBR",
                                    "useFileStager", "usePFCTurl", "accessmode=",
                                    "skipInputByRetry=","writeInputToTxt=",
                                    "rootVer=","enable-jem","jem-config=",
                                    ])
    except getopt.GetoptError, err:
        print '%s' % str(err)
        __usage__()
        sys.exit(0)
        
    for o, a in opts:
        if o == "-l":
            libraries=a
        if o == "-j":
            mexec=urllib.unquote(a)
        if o == "-r":
            runDir=a
        if o == "-p":
            jobParams=urllib.unquote(a)
        if o == "-i":
            exec "inputFiles="+a
        if o == "-f":
            exec "inputList="+a
        if o == "-o":
#            exec "outputFiles="+a
            outputFile = a
        if o == "-t":
            inputType = a
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
        if o == "--libTgz":
            libTgz  = a
        if o == "--parentDS":
            parentDS = a
        if o == "--parentContainer":
            parentContainer = a
        if o == "--outDS":
            outputDS = a

    # dump parameter
    try:
        print "=== parameters ==="
        print "libraries",libraries
        print "runDir",runDir
        print "jobParams",jobParams
        print "inputFiles",inputFiles
        print "inputList",inputList
        print "inputType",inputType
        print "mexec",mexec
        print "outputFile",outputFile
        print "inputGUIDs",inputGUIDs
        print "oldPrefix",oldPrefix
        print "newPrefix",newPrefix
        print "directIn",directIn
        print "usePFCTurl",usePFCTurl
        print "lfcHost",lfcHost
        print "debugFlag",debugFlag
        print "liveLog",liveLog
        print "sourceURL",sourceURL
        print "inMap",inMap
        print "useAthenaPackages",useAthenaPackages
        print "archiveJobO",archiveJobO
        print "dbrFile",dbrFile
        print "dbrRun",dbrRun
        print "notExpandDBR",notExpandDBR
        print "libTgz",libTgz
        print "parentDS",parentDS
        print "parentContainer",parentContainer
        print "outputDS",outputDS
        print "skipInputByRetry",skipInputByRetry
        print "writeInputToTxt",writeInputToTxt
        print "rootVer",rootVer
        print "useRootCore",useRootCore
        print "==================="
    except:
        type, value, traceBack = sys.exc_info()
        print 'ERROR: missing parameters : %s - %s' % (type,value)
        sys.exit(EC_MissingArg)

    ## checking parameters
    """        
    if not outputFile:
        print 'ERROR: output file not specified, use -o to specify it'
        sys.exit(EC_MissingArg)

    if inputType.lower() not in SUPP_TYPES:
        print 'ERROR: input type %s not supported for merging' % inputType
        sys.exit(EC_ITYPE_UNSUPPORTED)

    if inputList:
        if not os.path.exists(inputList):
            print 'ERROR: input list file %s not available' % inputList
            sys.exit(EC_IFILE_UNAVAILABLE)
        else:
            f = open( inputList, 'r')
            for l in map(lambda x:x.strip(), f.readlines()):
                inputFiles.append(l)
            f.close()
    """
    ## parsing PoolFileCatalog.xml produced by pilot
    turlsPFC = __resolvePoolFileCatalog__(PFC="PoolFileCatalog.xml")
    print turlsPFC

    ## getting TURLs for direct I/O
    directPFNs = {}
    if directIn:
        if usePFCTurl:
            # Use the TURLs from PoolFileCatalog.xml created by pilot
            print "===== GUIDs and TURLs in PFC ====="
            print turlsPFC
            directTmp = turlsPFC
        else:
            if lfcHost != '':
                directTmp = __getPFNsFromLFC__(lfcHost, inputGUIDs, old_prefix=oldPrefix, new_prefix=newPrefix)
            else:
                directTmp = __getPFNsFromLRC__(urlLRC, inputFiles, isGUID=False, old_prefix=oldPrefix, new_prefix=newPrefix)

        # collect LFNs
        for id in directTmp.keys():
            lfn = directTmp[id].split('/')[-1]
            lfn = re.sub('__DQ2-\d+$','',lfn)
            lfn = re.sub('^([^:]+:)','', lfn)
            directPFNs[lfn] = directTmp[id]

        print directPFNs

    # save current dir
    currentDir = os.getcwd()
    currentDirFiles = os.listdir('.')

    # get archiveJobO
    if archiveJobO != '':
        tmpStat = __fetch_toolbox__('%s/cache/%s' % (sourceURL,archiveJobO))
        if not tmpStat:
            print 'ERROR : failed to download %s' % archiveJobO
            sys.exit(EC_MERGE_ERROR)
    
    ## create and change to workdir
    print "Running in",currentDir
    workDir = os.path.join(currentDir, 'workDir')
    shutil.rmtree(workDir, ignore_errors=True)
    os.makedirs(workDir)
    os.chdir(workDir)

    ## expand library tarballs
    libs = []
    libs.append( libTgz )
    libs.append( libraries )
    libs.append( archiveJobO )

    for lib in libs:
        if lib == '':
            pass
        elif lib.startswith('/'):
            print commands.getoutput('tar xvfzm %s' % lib)
        else:
            print commands.getoutput('tar xvfzm %s/%s' % (currentDir,lib))

    ## compose athena/root environment setup command
    cmdEnvSetup = __cmd_setup_env__(workDir, rootVer)

    ## create and change to rundir
    commands.getoutput('mkdir -p %s' % runDir)
    os.chdir(runDir)

    # loop over all args
    EC = EC_OK
    outputFiles = []
    print
    print "===== into main loop ===="
    print
    for tmpArg in args:
        # option appended after args
        try:
            if tmpArg.startswith('-'):
                print
                print "escape since non arg found %s" % tmpArg
                break
        except:
            pass
        try:
            tmpInputs,outputFile = tmpArg.split(':')
        except:
            continue
        inputFiles = tmpInputs.split(',')
        inputType = __getMergeType__(inputFiles,mexec)
        print
        print ">>> start new chunk <<<"
        print "=== params ==="
        print 'inputFiles',inputFiles
        print 'outputFile',outputFile
        print 'inputType',inputType
        ## checking input file list and creating new input file list according to the IO type
        if inputFiles != []:
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
                    print '%s not exist' % inputFile

            inputFiles = newInputs
            if len(inputFiles) == 0:
                print 'ERROR : No input file is available'
                sys.exit(EC_NoInput)
            print "=== new inputFiles ==="
            print inputFiles
        print "=== run merging ==="
        ## run merging
        EC = __run_merge__(inputType, inputFiles, outputFile, cmdEnvSetup=cmdEnvSetup, userCmd=mexec, useFileStager=useFileStager)
        if EC != EC_OK:
            print "run_merge failed with %s" % EC
            break
        print "run_merge exited with %s" % EC
        print
        outputFiles.append(outputFile)

    print
    print "=== ls %s ===" % runDir
    print commands.getoutput('ls -l')
    print

    ## prepare output
    pfcName = 'PoolFileCatalog.xml'

    if EC == EC_OK:
        for outputFile in outputFiles:
            ## checking the availability of the output file
            if not os.path.exists(outputFile):

                print 'ERROR: merging process finished; but output not found: %s' % outputFile

                EC = EC_OFILE_UNAVAILABLE

            else:
                # copy results
                commands.getoutput('mv %s %s' % (outputFile, currentDir))

    ## create empty PoolFileCatalog.xml file if it's not available
    if not os.path.exists(pfcName):
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

    # copy all log files from merging program
    __exec__("cp *.log %s" % currentDir)

    # go back to current dir
    os.chdir(currentDir)
    
    # remove work dir
    commands.getoutput('rm -rf %s' % workDir)

    if EC == EC_OK:
        print 'merge script: success'
    else:
        print 'merge script: failed : StatusCode=%d' % EC

    sys.exit(EC)
