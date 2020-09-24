#!/usr/bin/env python

import re
import sys
import os
import ast
import glob
import os.path
import getopt
import shutil
import tarfile
import xml.dom.minidom
import traceback
try:
    import urllib.request as urllib
except ImportError:
    import urllib
import uuid
from pandawnutil.wnmisc.misc_utils import commands_get_status_output
from pandawnutil.root import root_utils

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
    print ('dir : %s' % os.getcwd())
    print ('exec: %s' % cmd)
    s,o = commands_get_status_output(cmd)
    print ('status: %s' % (s % 255))
    print ('stdout:\n%s' % o)
    return s,o

def __resolvePoolFileCatalog__(PFC='PoolFileCatalog.xml'):
    '''
    resolving the PoolFileCatalog.xml file produced by the pilot job
    '''
    # collect GUIDs from PoolFileCatalog
    turls = {}
    try:
        print ("===== PFC from pilot =====")
        tmpPcFile = open(PFC)
        print (tmpPcFile.read())
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
    except Exception as e:
        print ('ERROR : Failed to collect GUIDs : %s' % str(e))

    return turls


def __cmd_setup_env__(workDir, rootVer, cmtConfig):

    # create cmt dir to setup Athena
    setupEnv = ''

    if useAthenaPackages:
        if not useCMake:
            tmpDir = '%s/%s/cmt' % (workDir, str(uuid.uuid4()))
            print ("Making tmpDir",tmpDir)
            os.makedirs(tmpDir)
            # create requirements
            oFile = open(tmpDir+'/requirements','w')
            oFile.write('use AtlasPolicy AtlasPolicy-*\n')
            oFile.write('use PathResolver PathResolver-* Tools\n')
            oFile.close()
            # setup command
            setupEnv  = 'export CMTPATH=%s:$CMTPATH; ' % workDir
            setupEnv += 'cd %s; cat requirements; cmt config; source ./setup.sh; cd -; ' % tmpDir
        else:
            cmakeSetupDir = 'usr/*/*/InstallArea/*'
            print ("CMake setup dir : {0}".format(cmakeSetupDir))
            if len(glob.glob(cmakeSetupDir)) > 0:
                setupEnv = 'source {0}/setup.sh;'.format(cmakeSetupDir)
            else:
                print ('WARNING: CMake setup dir not found')
                setupEnv = ''

    # setup root
    if rootVer != '':
        rootBinDir = workDir + '/pandaRootBin'
        # use setup script if available
        if os.path.exists('%s/pandaUseCvmfSetup.sh' % rootBinDir):
            with open('%s/pandaUseCvmfSetup.sh' % rootBinDir) as iFile:
                tmpSetupEnvStr = iFile.read()
        else:
            rootCVMFS, tmpSetupEnvStr = root_utils.get_version_setup_string(rootVer, cmtConfig)
        setupEnv += tmpSetupEnvStr
        setupEnv += ' root.exe -q;'

    # RootCore
    if useRootCore:
        pandaRootCoreWD = os.path.abspath(runDir+'/__panda_rootCoreWorkDir')
        if os.path.exists('%s/RootCore/scripts/grid_run.sh' % pandaRootCoreWD):
            setupEnv += 'source %s/RootCore/scripts/grid_run.sh %s; ' % (pandaRootCoreWD,pandaRootCoreWD) 

    # TestArea
    setupEnv += "export TestArea=%s; " % workDir

    print ("=== setup command ===")
    print (setupEnv)
    print ('')
    print ("=== env ===")
    print (commands_get_status_output(setupEnv+'env')[-1])

    return setupEnv

def __fetch_toolbox__(url, maxRetry=3):
    '''
    getting the runMerge toolbox containing executables, librarys to run merging programs
    '''
    print ('=== getting sandbox ===')
    ick = False

    cmd = 'wget --no-check-certificate -t %d --waitretry=60 %s' % (maxRetry, url)
    rc, output = __exec__(cmd)

    if rc == 0:
        ick = True
    else:
        print ('ERROR: wget %s error: %s' % (url, output))
    print ('')
    return ick

def __cat_file__(fpath):
    '''
    print the text content of given fpath to stdout
    '''

    print ('=== cat %s ===' % fpath)

    if os.path.exists(fpath):

        f = open(fpath,'r')

        for l in map( lambda x:x.strip(), f.readlines()):
            print (l)

        f.close()

def __merge_root__(inputFiles, outputFile, cmdEnvSetup='', dumpFile=None):
    '''
    merging files with hmerge
    '''

    EC = 0

    print ('merging with hmerge ...')

    ftools = ['hmerge','fs_copy']

    for f in ftools:
        __exec__('cp %s/%s .; chmod +x %s' % (currentDir, f, f))

    cmd  = cmdEnvSetup

    cmd += ' export PATH=.:$PATH;'
    cmd += ' hmerge -f'
    cmd += ' -o %s' % outputFile
    cmd += ' %s'    % ' '.join(inputFiles)

    if dumpFile is not None:
        dumpFile.write(cmd + '\n')
        dumpFile.write('echo\n')
        return EC

    rc, output = __exec__(cmd, mergelog=True)

    if rc != 0:
        print ("ERROR: hmerge returns error code %d" % rc)
        EC = EC_MERGE_ERROR

    return EC

def __merge_tgz__(inputFiles, outputFile, cmdEnvSetup, dumpFile=None):
    '''
    merging (tgzed) files into a tgz tarball
    '''

    EC = 0

    if dumpFile is not None:
        for fname in inputFiles:
            dumpFile.write('tar rvfh tmp_{0} {1}\n'.format(outputFile, fname))
        dumpFile.write('gzip -f tmp_{0}\n'.format(outputFile))
        dumpFile.write('mv tmp_{0}.gz {0}\n'.format(outputFile))
        dumpFile.write('echo\n')
        return EC

    print ('merging with tgz ...')

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
            print ("ERROR: tarfile %s not created properly" % outputFile)
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

def __merge_trf__(inputFiles, outputFile, cmdEnvSetup, dumpFile=None):
    '''
    merging files with functions provided by PATJobTransforms
    '''

    EC = 0

    print ('merging with Merging_trf.py from PATJobTransforms ...')

    cmd = cmdEnvSetup + ' get_files -scripts Merging_trf.py'
    rc, output = __exec__(cmd)

    if rc != 0:
        print (output)
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

        if dumpFile is not None:
            dumpFile.write(cmd + '\n')
            dumpFile.write('echo\n')
            return EC

        rc,output = __exec__(cmd, mergelog=True)

        if rc != 0:
            print ("ERROR: Merging_trf returns error code %d" % rc)
            EC = EC_MERGE_ERROR

    return EC

def __merge_user__(inputFiles, outputFile, cmdEnvSetup, userCmd, dumpFile=None):
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

    print ('merging with user command %s ...' % userCmd_new)

    cmd  = cmdEnvSetup;

    cmd += ' export PATH=.:$PATH;'
    cmd += ' %s' % userCmd_new

    if dumpFile is not None:
        dumpFile.write(cmd + '\n')
        dumpFile.write('echo\n')
        return EC
    rc, output = __exec__(cmd, mergelog=True)

    if rc != 0:
        print ("ERROR: user merging command %s returns error code %d" % (userCmd_new, rc))
        EC = EC_MERGE_ERROR

    return EC

def __run_merge__(inputType, inputFiles, outputFile, cmdEnvSetup='', userCmd=None, dumpFile=None):
    '''
    all-in-one function to run different type of merging algorithms
    '''

    EC = 0

    if inputType in ['hist','ntuple']:
        EC = __merge_root__(inputFiles, outputFile, cmdEnvSetup, dumpFile)

    elif inputType in ['pool']:
        EC = __merge_trf__(inputFiles, outputFile, cmdEnvSetup, dumpFile)

    elif inputType in ['log', 'text']:
        EC = __merge_tgz__(inputFiles, outputFile, cmdEnvSetup, dumpFile)

    elif inputType in ['user']:
        if userCmd:
            EC = __merge_user__(inputFiles, outputFile, cmdEnvSetup, userCmd, dumpFile)
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
    cmtConfig = ''
    runDir    = '.'
    useRootCore = False
    useCMake = False

    ## default values introduced in runMerge
    inputType  = 'ntuple'
    outputFile = ''
    inputList  = ''
    libTgz     = ''
    parentDS   = ''
    parentContainer = ''
    outputDS   = ''
    preprocess = False
    postprocess = False

    # command-line argument parsing
    opts = None
    args = None

    print (sys.argv)

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
                                    "rootVer=", "enable-jem", "jem-config=", "cmtConfig=",
                                    "useCMake", "preprocess", "postprocess"
                                    ])
    except getopt.GetoptError as err:
        print (str(err))
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
            inputFiles = ast.literal_eval(a)
        if o == "-f":
            inputList = ast.literal_eval(a)
        if o == "-o":
            outputFile = a
        if o == "-t":
            inputType = a
        if o == "--debug":
            debugFlag = True
        if o == "--inputGUIDs":
            inputGUIDs = ast.literal_eval(a)
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
            inMap = ast.literal_eval(a)
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
        if o == "--cmtConfig":
            cmtConfig = a
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
        if o == "--useCMake":
            useCMake = True
        if o == "--preprocess":
            preprocess = True
        if o == "--postprocess":
            postprocess = True

    # dump parameter
    try:
        print ("=== parameters ===")
        print ("libraries",libraries)
        print ("runDir",runDir)
        print ("jobParams",jobParams)
        print ("inputFiles",inputFiles)
        print ("inputList",inputList)
        print ("inputType",inputType)
        print ("mexec",mexec)
        print ("outputFile",outputFile)
        print ("inputGUIDs",inputGUIDs)
        print ("oldPrefix",oldPrefix)
        print ("newPrefix",newPrefix)
        print ("directIn",directIn)
        print ("usePFCTurl",usePFCTurl)
        print ("lfcHost",lfcHost)
        print ("debugFlag",debugFlag)
        print ("liveLog",liveLog)
        print ("sourceURL",sourceURL)
        print ("inMap",inMap)
        print ("useAthenaPackages",useAthenaPackages)
        print ("archiveJobO",archiveJobO)
        print ("dbrFile",dbrFile)
        print ("dbrRun",dbrRun)
        print ("notExpandDBR",notExpandDBR)
        print ("libTgz",libTgz)
        print ("parentDS",parentDS)
        print ("parentContainer",parentContainer)
        print ("outputDS",outputDS)
        print ("skipInputByRetry",skipInputByRetry)
        print ("writeInputToTxt",writeInputToTxt)
        print ("rootVer",rootVer)
        print ("cmtConfig", cmtConfig)
        print ("useRootCore",useRootCore)
        print ("useCMake",useCMake)
        print ("preprocess", preprocess)
        print ("postprocess", postprocess)
        print ("===================")
    except Exception as e:
        print ('ERROR: missing parameters : %s' % str(e))
        sys.exit(EC_MissingArg)

    if not postprocess:
        ## parsing PoolFileCatalog.xml produced by pilot
        turlsPFC = __resolvePoolFileCatalog__(PFC="PoolFileCatalog.xml")
        print (turlsPFC)

        ## getting TURLs for direct I/O
        directPFNs = {}
        if directIn:
            # Use the TURLs from PoolFileCatalog.xml created by pilot
            print ("===== GUIDs and TURLs in PFC =====")
            print (turlsPFC)
            directTmp = turlsPFC
            # collect LFNs
            for id in directTmp.keys():
                lfn = directTmp[id].split('/')[-1]
                lfn = re.sub('__DQ2-\d+$','',lfn)
                lfn = re.sub('^([^:]+:)','', lfn)
                directPFNs[lfn] = directTmp[id]
            print (directPFNs)

        # get archiveJobO
        if archiveJobO != '':
            tmpStat = __fetch_toolbox__('%s/cache/%s' % (sourceURL,archiveJobO))
            if not tmpStat:
                print ('ERROR : failed to download %s' % archiveJobO)
                sys.exit(EC_MERGE_ERROR)

    # save current dir
    currentDir = os.getcwd()
    currentDirFiles = os.listdir('.')

    
    ## create and change to workdir
    print ('')
    print ("Running in %s " % currentDir)
    workDir = os.path.join(currentDir, 'workDir')
    if not postprocess:
        shutil.rmtree(workDir, ignore_errors=True)
        os.makedirs(workDir)
    os.chdir(workDir)

    if not postprocess:
        ## expand library tarballs
        libs = []
        libs.append( libTgz )
        libs.append( libraries )
        libs.append( archiveJobO )

        for lib in libs:
            if lib == '':
                pass
            elif lib.startswith('/'):
                print (commands_get_status_output('tar xvfzm %s' % lib)[-1])
            else:
                print (commands_get_status_output('tar xvfzm %s/%s' % (currentDir,lib))[-1])

        ## compose athena/root environment setup command
        cmdEnvSetup = __cmd_setup_env__(workDir, rootVer, cmtConfig)

        ## create and change to rundir
        commands_get_status_output('mkdir -p %s' % runDir)
    os.chdir(runDir)

    # make dump file for preprocess
    dumpFileName = os.path.join(currentDir, '__run_main_exec.sh')
    dumpFile = None
    if preprocess:
        dumpFile = open(dumpFileName, 'w')
        dumpFile.write('cd {0}\n'.format(os.path.relpath(os.getcwd(), currentDir)))

    # loop over all args
    EC = EC_OK
    outputFiles = []
    print ('')
    print ("===== into main loop ====")
    print ('')
    for tmpArg in args:
        # option appended after args
        try:
            if tmpArg.startswith('-'):
                print ('')
                print ("escape since non arg found %s" % tmpArg)
                break
        except:
            pass
        try:
            tmpInputs,outputFile = tmpArg.split(':')
        except:
            continue
        inputFiles = tmpInputs.split(',')
        inputType = __getMergeType__(inputFiles,mexec)
        if not postprocess:
            print (">>> start new chunk <<<")
            print ("=== params ===")
            print ('inputFiles',inputFiles)
            print ('outputFile',outputFile)
            print ('inputType',inputType)
            ## checking input file list and creating new input file list according to the IO type
            if inputFiles != []:
                print ("=== check input files ===")
                newInputs = []
                inputFileMap = {}
                for inputFile in inputFiles:
                    # direct reading
                    foundFlag = False
                    if directIn:
                        if inputFile in directPFNs:
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
                        print ('%s not exist' % inputFile)

                inputFiles = newInputs
                if len(inputFiles) == 0:
                    print ('ERROR : No input file is available')
                    sys.exit(EC_NoInput)
                print ("=== new inputFiles ===")
                print (inputFiles)
            if not preprocess:
                print ("=== run merging ===")
            else:
                print ("=== writing command ===")
            ## run merging
            EC = __run_merge__(inputType, inputFiles, outputFile, cmdEnvSetup=cmdEnvSetup, userCmd=mexec,
                               dumpFile=dumpFile)
            if EC != EC_OK:
                print ("run_merge failed with %s" % EC)
                break
            if not preprocess:
                print ("run_merge exited with %s" % EC)
            else:
                print ("done")
            print ('')
        outputFiles.append(outputFile)

    if preprocess:
        print ("=== Results ===")
        dumpFile.close()
        commands_get_status_output('chmod +x {0}'.format(dumpFileName))
        print ('merge preprocess succeeded')
        print ('produced {0}'.format(dumpFileName))
        sys.exit(0)

    print ('')
    print ("=== ls in run dir : %s (%s) ===" % (runDir, os.getcwd()))
    print (commands_get_status_output('ls -l')[-1])
    print ('')

    ## prepare output
    pfcName = 'PoolFileCatalog.xml'

    if EC == EC_OK:
        for outputFile in outputFiles:
            ## checking the availability of the output file
            if not os.path.exists(outputFile):

                print ('ERROR: merging process finished; but output not found: %s' % outputFile)

                EC = EC_OFILE_UNAVAILABLE

            else:
                # copy results
                commands_get_status_output('mv %s %s' % (outputFile, currentDir))

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
    commands_get_status_output('mv %s %s' % (pfcName,currentDir))

    # copy all log files from merging program
    print ("=== copy log files ===")
    __exec__("cp *.log %s" % currentDir)

    # go back to current dir
    os.chdir(currentDir)

    print ("=== ls in %s ===" % os.getcwd())
    print (commands_get_status_output('ls -l')[-1])
    print ('')
    # remove work dir
    commands_get_status_output('rm -rf %s' % workDir)

    if EC == EC_OK:
        print ('merge script: success')
    else:
        print ('merge script: failed : StatusCode=%d' % EC)

    sys.exit(EC)
