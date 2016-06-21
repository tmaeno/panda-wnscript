#!/bin/bash

"exec" "python" "-u" "$0" "$@"

import os
import re
import sys
import time
import getopt
import urllib
import commands

# error code
EC_MissingArg  = 10
EC_CMTFailed   = 20
EC_NoTarball   = 30

print "--- start ---"
print time.ctime()

debugFlag = False
sourceURL = 'https://gridui01.usatlas.bnl.gov:25443'
runDir    = ''
bexec     = ''
useAthenaPackages = False
rootVer   = ''
useRootCore = False
cmtConfig = ''
noCompile = False
useMana   = False
manaVer   = ''
useCMake  = False

# command-line parameters
opts, args = getopt.getopt(sys.argv[1:], "i:o:u:r:",
                           ["pilotpars","debug","oldPrefix=","newPrefix=",
                            "directIn","sourceURL=","lfcHost=","envvarFile=",
			    "bexec=","useAthenaPackages",
                            "useFileStager","accessmode=",
			    "rootVer=","useRootCore","cmtConfig=",
                            "noCompile","useMana","manaVer=",
                            "useCMake"])
for o, a in opts:
    if o == "-i":
        sources = a
    if o == "-o":
        libraries = a
    if o == "-r":
        runDir = a
    if o == "--bexec":
        bexec = urllib.unquote(a)
    if o == "--debug":
        debugFlag = True
    if o == "--sourceURL":
        sourceURL = a
    if o == "--useAthenaPackages":
        useAthenaPackages = True
    if o == "--rootVer":
        rootVer = a 
    if o == "--useRootCore":
        useRootCore = True
    if o == "--cmtConfig":
        cmtConfig = a
    if o == "--noCompile":
        noCompile = True
    if o == "--useMana":
        useMana = True
    if o == "--manaVer":
        manaVer = a
    if o == "--useCMake":
        useCMake = True


# dump parameter
try:
    print "sources",sources
    print "libraries",libraries
    print "debugFlag",debugFlag
    print "sourceURL",sourceURL
    print "runDir",runDir
    print "bexec",bexec
    print "useAthenaPackages",useAthenaPackages
    print "rootVer",rootVer
    print "useRootCore",useRootCore
    print "cmtConfig",cmtConfig
    print "noCompile",noCompile
    print "useMana",useMana
    print "manaVer",manaVer
    print "useCMake",useCMake
except:
    sys.exit(EC_MissingArg)

# save current dir
currentDir = os.getcwd()

print "Running in",currentDir

print "--- wget ---"
print time.ctime()

# get input file
def getFileViaHttp(tmpSourceURL,tmpSources,tmpFullURL):
    output = commands.getoutput('wget -h')
    #print output
    wgetCommand = 'wget'
    for line in output.split('\n'):
        if re.search('--no-check-certificate',line) != None:
            wgetCommand = 'wget --no-check-certificate'
            break
    print wgetCommand
    if tmpFullURL == '':
        tmpURL = "%s/cache/%s" % (tmpSourceURL,tmpSources)
    else:
        tmpURL = tmpFullURL
    nTry = 3
    print '%s %s' % (wgetCommand,tmpURL)
    for iTry in range(nTry):
        print 'Try : %s' % iTry
        status,output = commands.getstatusoutput('%s %s' % (wgetCommand,tmpURL))
        print output
        if status == 0:
            break
        if iTry+1 < nTry:
            time.sleep(30)

    if not os.path.exists(tmpSources):
        print "wget did not work, try curl"
        cmd = 'curl --insecure -f -sS -o %s %s' % (tmpSources,tmpURL)
        print cmd
        print commands.getoutput(cmd)

    if not os.path.exists(tmpSources):
        print 'ERROR : unable to fetch %s from web' % tmpSources
        sys.exit(EC_NoTarball)

# compile Athena packages
if useAthenaPackages and not noCompile:
    # get TRF
    trfName    = 'buildJob-00-00-03'
    trfBaseURL = 'http://pandaserver.cern.ch:25080/trf/user/'
    getFileViaHttp('',trfName,trfBaseURL+trfName)
    # execute
    commands.getoutput('chmod +x %s' % trfName)
    tmpLibName = 'tmplib.%s' % commands.getoutput('uuidgen 2>/dev/null')
    com = "./%s -i %s -o %s --debug --sourceURL %s " % (trfName,sources,tmpLibName,sourceURL)
    if useCMake:
        com += '--useCMake '
    print "--- Compile Athena packages ---"
    print time.ctime()
    if debugFlag:
        status = os.system(com)
    else:
        status,output = commands.getstatusoutput(com)
        print output
    commands.getoutput('rm -f %s' % tmpLibName)    
    status %= 255    
    if status != 0:
        print "--- failed to compile Athena packages %s ---" % status
        print time.ctime()
        # return
        sys.exit(status)
    print "--- Successfully compiled Athena packages ---"
    print time.ctime()
else:
    # get source files
    getFileViaHttp(sourceURL,sources,'')

# get root
useCvmfsROOT = False
if rootVer != '':
    if rootVer.count('.') != 2:
        rootVer += ".00"
    rootTgz = "root_v" + rootVer    
    # 32 or 64
    if cmtConfig in ['x86_64-slc5-gcc43-opt']:
        rootTgz += ".Linux-slc5_amd64-gcc4.3.tar.gz"
        rootCVMFS = rootVer + '-x86_64-slc5-gcc4.3'
    else:
        rootTgz += ".Linux-slc5-gcc4.3.tar.gz"
        rootCVMFS = rootVer + '-i686-slc5-gcc4.3'
    rootCVMFS = '/cvmfs/atlas.cern.ch/repo/ATLASLocalRootBase/x86_64/root/%s' % rootCVMFS
    # check CVMFS
    tmpStat,tmpOut = commands.getstatusoutput('ls -l %s/bin/thisroot.sh' % rootCVMFS)
    tmpStat %= 255
    print "Check availability of ROOT in %s" % rootCVMFS
    print tmpOut
    if tmpStat == 0:
        print "use CVMFS for rootVer"
        useCvmfsROOT = True
    else:
        print "use PandaCache for rootVer"
        getFileViaHttp('',rootTgz,'http://pandacache.cern.ch:25080/appdir/'+rootTgz)
        
# goto work dir
workDir = currentDir + '/workDir'
if not useAthenaPackages:
    print commands.getoutput('rm -rf %s' % workDir)
    os.makedirs(workDir)
print "Goto workDir",workDir
os.chdir(workDir)

# expand root 
if rootVer != '':
    rootBinDir = workDir + '/pandaRootBin'
    os.makedirs(rootBinDir)
    if not useCvmfsROOT:
        os.chdir(rootBinDir)
        commands.getoutput('tar xvfzm %s/%s' % (currentDir,rootTgz))
        os.chdir(workDir)

# expand sources
if not useAthenaPackages or noCompile:
    print "--- expand source ---"
    print time.ctime()
    if sources.startswith('/'):
        out = commands.getoutput('tar xvfzm %s' % sources)
    else:
        out = commands.getoutput('tar xvfzm %s/%s' % (currentDir,sources))
    print out

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
    if useCvmfsROOT:
        tmpSetupEnvStr  = "export ATLAS_LOCAL_ROOT_BASE=/cvmfs/atlas.cern.ch/repo/ATLASLocalRootBase; "
        tmpSetupEnvStr += "source $ATLAS_LOCAL_ROOT_BASE/user/atlasLocalSetup.sh --quiet; "
        tmpSetupEnvStr += "source $ATLAS_LOCAL_ROOT_BASE/packageSetups/atlasLocalROOTSetup.sh --rootVersion=%s --skipConfirm; " % rootCVMFS.split('/')[-1]
        setupEnv += tmpSetupEnvStr
        setupEnv += "root.exe -q; "
        # keep setup str for runGen
        oFile = open('%s/pandaUseCvmfSetup.sh' % rootBinDir,'w')
        oFile.write(tmpSetupEnvStr)
        oFile.close()
    else:
        setupEnv += ' export ROOTSYS=%s/root; export PATH=$ROOTSYS/bin:$PATH; export LD_LIBRARY_PATH=$ROOTSYS/lib:$LD_LIBRARY_PATH; root.exe -q; ' % \
                    rootBinDir

# init status
status = 0

# mana
if useMana:
    tmpSetupEnvMana  = "export ATLAS_LOCAL_ROOT_BASE=/cvmfs/atlas.cern.ch/repo/ATLASLocalRootBase; "
    tmpSetupEnvMana += "source $ATLAS_LOCAL_ROOT_BASE/user/atlasLocalSetup.sh --quiet; "
    tmpSetupEnvMana += "source $ATLAS_LOCAL_ROOT_BASE/packageSetups/atlasLocalManaSetup.sh --manaVersion ${manaVersionVal}; "
    tmpSetupEnvMana += "hwaf asetup mana %s; " % manaVer
    setupEnv += tmpSetupEnvMana
    setupEnv += 'hwaf show setup; '
    compileExec = 'hwaf configure; hwaf '
    print "--- print env ---"
    os.system(setupEnv+'env')
    print "--- setup mana ---"    
    print setupEnv+compileExec
    status = os.system(setupEnv+compileExec)
    status %= 255
    if status != 0:
        print "ERROR : failed to setup mana"
                                        
    
# make if needed
if status == 0 and (bexec != '' or useRootCore):
    if not useMana:
        print "--- print env ---"
        print commands.getoutput(setupEnv+'env')    
    print "--- make ---"
    print time.ctime()
    # make rundir just in case
    if runDir != '':
        commands.getoutput('mkdir %s' % runDir)
    # go to run dir
    os.chdir(runDir)
    print "PWD=%s" % os.getcwd()
    # add current dir to PATH
    os.environ['PATH'] = '.:'+os.environ['PATH']
    # make RootCore
    compileExec = ''
    if useRootCore:
	pandaRootCoreWD = os.path.abspath('%s/__panda_rootCoreWorkDir' % os.getcwd())
        if noCompile:
            compileExec = 'source %s/RootCore/scripts/grid_compile_nobuild.sh %s' % (pandaRootCoreWD,pandaRootCoreWD)
        else:
            compileExec = 'source %s/RootCore/scripts/grid_compile.sh %s' % (pandaRootCoreWD,pandaRootCoreWD)
    if bexec != '':                
        # chmod +x just in case
        commands.getoutput('chmod +x %s' % bexec.split()[0])
        if compileExec != '':
            compileExec = compileExec + '; ' + bexec
	else:
            compileExec = bexec
    # execute
    if compileExec != '':
        print "execute : "+setupEnv+compileExec
        if debugFlag:
            status = os.system(setupEnv+compileExec)
        else:
            status,out = commands.getstatusoutput(setupEnv+compileExec)
            print out
        status %= 255
        if status != 0:
            print "ERROR : make failed"
    # back to workdir
    os.chdir(workDir)

print "--- archive libraries ---"
print time.ctime()

# archive
if libraries.startswith('/'):
    commands.getoutput('tar cvfz %s *' % libraries)
else:
    commands.getoutput('tar cvfz %s/%s *' % (currentDir,libraries))

# go back to current dir
os.chdir(currentDir)

# remove workdir
if not debugFlag:
    commands.getoutput('rm -rf %s' % workDir)

# remove root
if rootVer != '':
    commands.getoutput('rm -rf %s' % rootTgz)
    
print "--- finished with %s ---" % status
print time.ctime()

# return
sys.exit(status)
