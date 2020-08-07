#!/bin/bash

"exec" "python" "-u" "$0" "$@"

"""
Build job

Usage:

source $SITEROOT/setup.sh
source $T_DISTREL/AtlasRelease/*/cmt/setup.sh -tag_add=???
buildJob.py -i [sources] -o [libraries] 

[sources]   : an archive which contains source files.
              each file path must be relative to $CMTHOME 
[libraries] : an archive which will contain compiled libraries.
              each file path is relative to $CMTHOME.
              absolute paths in InstallArea are changed to relative paths
              except for externals.

Procedure:

* create a tmp dir for 'cmt broadcast'
* expand sources
* make a list of packages
* create requirements in the tmp dir
* do 'cmt broadcast' in the tmp dir
* change absolute paths in InstallArea to be relative
* archive

"""

import os
import re
import sys
import time
import uuid
import getopt
import subprocess
try:
    from urllib.request import urlopen
    from urllib.error import HTTPError
except ImportError:
    from urllib2 import urlopen, HTTPError
from pandawnutil.wnmisc.misc_utils import commands_get_status_output, get_file_via_http, record_exec_directory,\
    propagate_missing_sandbox_error


# error code
EC_MissingArg  = 10
EC_CMTFailed   = 20
EC_NoTarball   = 30

print ("--- start ---")
print (time.ctime())

debugFlag = False
sourceURL = 'https://gridui01.usatlas.bnl.gov:25443'
noCompile = False
useCMake = False

# command-line parameters
opts, args = getopt.getopt(sys.argv[1:], "i:o:u:",
                           ["pilotpars","debug","oldPrefix=","newPrefix=",
                            "directIn","sourceURL=","lfcHost=","envvarFile=",
                            "useFileStager","accessmode=","copytool=",
                            "noCompile","useCMake"])
for o, a in opts:
    if o == "-i":
        sources = a
    if o == "-o":
        libraries = a
    if o == "--debug":
        debugFlag = True
    if o == "--sourceURL":
        sourceURL = a
    if o == "--noCompile":
        noCompile = True
    if o == "--useCMake":
        useCMake = True

# dump parameter
try:
    print ("sources", sources)
    print ("libraries", libraries)
    print ("debugFlag", debugFlag)
    print ("sourceURL", sourceURL)
    print ("noCompile", noCompile)
    print ("useCMake", useCMake)
except:
    sys.exit(EC_MissingArg)


# save current dir
currentDir = record_exec_directory()

print (time.ctime())

url = '%s/cache/%s' % (sourceURL, sources)
tmpStat, tmpOut = get_file_via_http(full_url=url)
if not tmpStat:
    print ("ERROR : " + tmpOut)
    propagate_missing_sandbox_error()
    sys.exit(EC_NoTarball)

# goto work dir
workDir = currentDir + '/workDir'
print (commands_get_status_output('rm -rf %s' % workDir)[-1])
os.makedirs(workDir)
print ("--- Goto workDir %s ---\n" % workDir)
os.chdir(workDir)

# cmake
if useCMake:
    # go back to current dir
    os.chdir(currentDir)
    print ("--- Checking tarball for CMake ---\n")
    os.rename(sources,libraries)
    if debugFlag:
        # expand 
        tmpStat = subprocess.call('tar xvfzm {0}'.format(libraries),shell=True)
    else:
        tmpStat = subprocess.call('tar tvfz {0}'.format(libraries),shell=True)
    if tmpStat != 0:
        print ("")
        print ("ERROR : check with tar tvfz gave non-zero return code")
        print ("ERROR : {0} is corrupted".format(sources))
        propagate_missing_sandbox_error()
        sys.exit(EC_NoTarball)
    print ("\n--- finished ---")
    print (time.ctime())
    # return
    sys.exit(0)

# crate tmpdir
tmpDir = str(uuid.uuid4()) + '/cmt'
print ("--- Making tmpDir ---",tmpDir)
os.makedirs(tmpDir)

print ("--- expand source ---")
print (time.ctime())

# expand sources
if sources.startswith('/'):
    tmpStat, out = commands_get_status_output('tar xvfzm %s' % sources)
else:
    tmpStat, out = commands_get_status_output('tar xvfzm %s/%s' % (currentDir,sources))
print (out)
if tmpStat != 0:
    print ("ERROR : {0} is corrupted".format(sources))
    sys.exit(EC_NoTarball)

# check if groupArea exists
groupFile = re.sub('^sources','groupArea',sources)
groupFile = re.sub('\.gz$','',groupFile)
useGroupArea = False
if os.path.exists("%s/%s" % (workDir,groupFile)):
    useGroupArea = True
    # make groupArea
    groupAreaDir = currentDir + '/personal/groupArea'
    commands_get_status_output('rm -rf %s' % groupAreaDir)
    os.makedirs(groupAreaDir)
    # goto groupArea
    print ("Goto groupAreaDir",groupAreaDir)
    os.chdir(groupAreaDir)
    # expand groupArea
    print (commands_get_status_output('tar xvfm %s/%s' % (workDir,groupFile))[-1])
    # make symlink to InstallArea
    os.symlink('%s/InstallArea' % workDir, 'InstallArea')
    # back to workDir
    os.chdir(workDir)

# list packages
packages=[]
for line in out.splitlines():
    name = line.split()[-1]
    if name.endswith('/cmt/') and not '__panda_rootCoreWorkDir' in name:
        # remove /cmt/
        name = re.sub('/cmt/$','',name)
        packages.append(name)

# create requirements
oFile = open(tmpDir+'/requirements','w')
oFile.write('use AtlasPolicy AtlasPolicy-*\n')
useVersionDir = False
# append user packages
for pak in packages:
    # version directory
    vmat = re.search('-\d+-\d+-\d+$',pak)
    if vmat:
        useVersionDir = True
        mat = re.search('^(.+)/([^/]+)/([^/]+)$',pak)
        if mat:
            oFile.write('use %s %s %s\n' % (mat.group(2),mat.group(3),mat.group(1)))
        else:
            mat = re.search('^(.+)/([^/]+)$',pak)
            if mat:
                oFile.write('use %s %s\n' % (mat.group(1),mat.group(2)))
            else:
                oFile.write('use %s\n' % pak)
    else:                                
        mat = re.search('^(.+)/([^/]+)$',pak)
        if mat:
            oFile.write('use %s %s-* %s\n' % (mat.group(2),mat.group(2),mat.group(1)))
        else:
            oFile.write('use %s\n' % pak)
oFile.close()

# OS release
print ("--- /etc/redhat-release ---")
tmp = commands_get_status_output('cat /etc/redhat-release')[-1]
print (tmp)
match = re.search('(\d+\.\d+[\d\.]*)\s+\([^\)]+\)',tmp)
osRelease = ''
if match is not None:
    osRelease = match.group(1)
print ("Release -> %s" % osRelease)
# processor
print ("--- uname -p ---")
processor = commands_get_status_output('uname -p')[-1]
print (processor)
# cmt config
print ("--- CMTCONFIG ---")
cmtConfig = commands_get_status_output('echo $CMTCONFIG')[-1]
print (cmtConfig)
# compiler
print ("--- gcc ---")
tmp = commands_get_status_output('gcc -v')[-1]
print (tmp)
match = re.search('gcc version (\d+\.\d+[^\s]+)',tmp.split('\n')[-1])
gccVer = ''
if match is not None:
    gccVer = match.group(1)
print ("gcc -> %s" % gccVer)
# check if g++32 is available
print ("--- g++32 ---")
s32,o32 = commands_get_status_output('which g++32')
print (s32)
print (o32)
# make alias of gcc323 for SLC4
gccAlias = ''
if s32 == 0 and osRelease != '' and osRelease >= '4.0':
    # when CMTCONFIG has slc3-gcc323
    if cmtConfig.find('slc3-gcc323') != -1:
        # unset alias when gcc ver is unknown or already has 3.2.3
        if not gccVer in ['','3.2.3']:
            # 64bit or not
            if processor == 'x86_64':
                gccAlias = 'echo "%s -m32 \$*" > g++;' % o32
            else:
                gccAlias = 'echo "%s \$*" > g++;' % o32
            gccAlias += 'chmod +x g++; export PATH=%s/%s:$PATH;' % (workDir,tmpDir)
print ("--- gcc alias ---")
print ("      ->  %s" % gccAlias)
                
print ("--- compile ---")
print (time.ctime())

if not useGroupArea:
    # append workdir to CMTPATH
    env = 'CMTPATH=%s:$CMTPATH' % os.getcwd()
else:
    # append workdir+groupArea to CMTPATH
    env = 'CMTPATH=%s:%s:$CMTPATH' % (os.getcwd(),groupAreaDir)
# use short basename 
symLinkRel = ''
try:
    # get tmp dir name
    tmpDirName = ''
    if 'EDG_TMP' in os.environ:
        tmpDirName = os.environ['EDG_TMP']
    elif 'OSG_WN_TMP' in os.environ:
        tmpDirName = os.environ['OSG_WN_TMP']
    else:
        tmpDirName = '/tmp'
    # make symlink
    if 'SITEROOT' in os.environ:
        # use /tmp if it is too long. 10 is the length of tmp filename
        if len(tmpDirName)+10 > len(os.environ['SITEROOT']):
            print ("INFO : use /tmp since %s is too long" % tmpDirName)
            tmpDirName = '/tmp'
        # make tmp file first
        import tempfile
        tmpFD,tmpPathName = tempfile.mkstemp(dir=tmpDirName)
        os.close(tmpFD)
        # change tmp file to symlink
        tmpS,tmpO = commands_get_status_output('ln -fs %s %s' % (os.environ['SITEROOT'],tmpPathName))
        if tmpS != 0:
            print (tmpO)
            print ("WARNING : cannot make symlink %s %s" % (os.environ['SITEROOT'],tmpPathName))
            # remove
            os.remove(tmpPathName)
        else:
            # compare length
            if len(tmpPathName) < len(os.environ['SITEROOT']):
                shortCMTPATH = os.environ['CMTPATH'].replace(os.environ['SITEROOT'],tmpPathName)
                # set path name
                symLinkRel = tmpPathName
            else:
                print ("WARNING : %s is shorter than %s" % (os.environ['SITEROOT'],tmpPathName))
                # remove
                os.remove(tmpPathName)
except Exception as e:
    print ('WARNING : failed to make short CMTPATH due to %s' % str(e))
                
# construct command
com  = ''
if symLinkRel != '':
    com += 'export SITEROOT=%s;export CMTPATH=%s;' % (symLinkRel,shortCMTPATH)
    if 'CMTPROJECTPATH' in os.environ and os.environ['SITEROOT'] == os.environ['CMTPROJECTPATH']:
        com += 'export CMTPROJECTPATH=%s;' % symLinkRel
com += 'export %s;' % env
com += 'cmt config;'
com += 'source ./setup.sh; source ./setup.sh;'
if gccAlias != '':
    com += gccAlias
if useVersionDir:
    com += 'export CMTSTRUCTURINGSTYLE=with_version_directory;'
com += 'export TestArea=%s;' % workDir
comConf = com
com += 'env; cmt br cmt config;'
com += 'cmt br make'
comConf += 'cmt br "rm -rf ../genConf";'
comConf += 'cmt br make'

# do cmt under tmp dir
if not noCompile:
    print ("cmt:", com)
    os.chdir(tmpDir)
    if not debugFlag:
        status,out = commands_get_status_output(com)
        print (out)
        # look for error since cmt doesn't set error code when make failed
        if status == 0:
            try:
                for line in out.split('\n')[-3:]:
                    if line.startswith('make') and re.search('Error \d+$',line) is not None:
                        status = 1
                        print ("ERROR: make failed. set status=%d" % status)
                        break
            except Exception:
                pass
    else:
        status = os.system(com)    
    if status:
        print ("ERROR: CMT failed : %d" % status)
        sys.exit(EC_CMTFailed)

    # copy so for genConf
    print ('')
    print ("==== copy so")
    # sleep for touch
    time.sleep(120)
    for pak in packages:
        try:
            # look for so
            srcSoDir = '%s/%s/%s' % (workDir,pak,cmtConfig)
            dstSoDir = '%s/InstallArea/%s/lib' % (workDir,cmtConfig)
            srcSoFiles = os.listdir(srcSoDir)
            for srcSoFile in srcSoFiles:
                if srcSoFile.endswith('.so') or srcSoFile.endswith('.dsomap'):
                    # remove symlink
                    com = "rm -fv %s/%s" % (dstSoDir,srcSoFile)
                    print (com)
                    print (commands_get_status_output(com)[-1])
                    # copy so
                    com = "cp -v %s/%s %s" % (srcSoDir,srcSoFile,dstSoDir) 
                    print (com)
                    print (commands_get_status_output(com)[-1])
                    # update timestamp to prevent creating symlink again
                    com = "touch %s/%s" % (dstSoDir,srcSoFile) 
                    print (com)
                    print (commands_get_status_output(com)[-1])
        except Exception as e:
            print ("ERROR: in copy so : %s" % str(e))

    # check lib dir before
    com = 'ls -l %s/InstallArea/%s/lib' % (workDir,cmtConfig)
    print ("==== %s" % com)
    print (commands_get_status_output(com)[-1])

    # run make again for genConf
    print ("==== run genConf again")
    print (comConf)
    print (commands_get_status_output(comConf)[-1])

    # check lib dir after
    com = 'ls -l %s/InstallArea/%s/lib' % (workDir,cmtConfig)
    print ("==== %s" % com)
    print (commands_get_status_output(com)[-1])

# go back to work dir
os.chdir(workDir)

# change absolute paths in InstallArea to relative paths
fullPathList = []
def reLink(dir,dirPrefix):
    try:
        # get files
        flist=os.listdir(dir)
        dirPrefix = dirPrefix+'/..'
        # save the current dir
        curDir = os.getcwd()
        os.chdir(dir)
        for item in flist:
            # if symbolic link
            if os.path.islink(item):
                # change full path to relative path
                fullPath = os.readlink(item)
                # check if it is already processed, to avoid an infinite loop
                if fullPath in fullPathList:
                    continue
                fullPathList.append(fullPath)
                # remove special characters from comparison string
                sString=re.sub('[\+]','.',workDir)
                # replace
                relPath = re.sub('^%s/' % sString, '', fullPath)
                if relPath != fullPath:
                    # re-link
                    os.remove(item)
                    os.symlink('%s/%s' % (dirPrefix,relPath), item)
            # if directory
            if os.path.isdir(item):
                reLink(item,dirPrefix)
        # back to the previous dir
        os.chdir(curDir)
    except Exception as e:
        print ("ERROR: in reLink(%s) : %s" % str(e))


# execute reLink()
for item in os.listdir('.'):
    if os.path.isdir(item):
        reLink(item,'.')

# remove tmp dir
commands_get_status_output('rm -rf %s' % re.sub('/cmt$','',tmpDir))

print ("--- archive libraries ---")
print (time.ctime())

# archive
if libraries.startswith('/'):
    commands_get_status_output('tar cvfz %s *' % libraries)
else:
    commands_get_status_output('tar cvfz %s/%s *' % (currentDir,libraries))

# go back to current dir
os.chdir(currentDir)

# remove work dir
if not debugFlag:
    commands_get_status_output('rm -rf %s' % workDir)
    # remove groupArea
    if useGroupArea:
        commands_get_status_output('rm -rf %s' % groupAreaDir)

# remove symlink for rel
if symLinkRel != '':
    commands_get_status_output('rm -rf %s' % symLinkRel)

print ("--- finished ---")
print (time.ctime())

# return
sys.exit(0)
