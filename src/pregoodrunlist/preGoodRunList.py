#!/bin/bash

"exec" "python" "-u" "$0" "$@"

import os
import re
import sys
import time
import optparse
import commands

from pandawnutil.wnlogger import PLogger
from pandawnutil.wnmisc import PsubUtils

# error code
EC_MissingArg  = 10
EC_WGET        = 146
EC_GRL         = 147

# set TZ
os.environ['TZ'] = 'UTC'

optP = optparse.OptionParser(conflict_handler="resolve")
optP.add_option('-v', action='store_const', const=True, dest='verbose',  default=False,
                help='Verbose')
optP.add_option('-d', action='store_const', const=True, dest='debug',  default=False,
                help='Debug')
optP.add_option('--sourceURL',action='store',dest='sourceURL',default='',
                type='string', help='base URL where run/event list is retrived')
optP.add_option('--goodRunListXML', action='store', dest='goodRunListXML', default='',
                type='string', help='Good Run List XML which will be converted to datasets by AMI')
optP.add_option('--goodRunListDataType', action='store', dest='goodRunDataType', default='',
                type='string', help='specify data type when converting Good Run List XML to datasets, e.g, AOD (default)')
optP.add_option('--goodRunListProdStep', action='store', dest='goodRunProdStep', default='',
                type='string', help='specify production step when converting Good Run List to datasets, e.g, merge (default)')
optP.add_option('--goodRunListDS', action='store', dest='goodRunListDS', default='',
                type='string', help='A comma-separated list of pattern strings. Datasets which are converted from Good Run List XML will be used when they match with one of the pattern strings. Either \ or "" is required when a wild-card is used. If this option is omitted all datasets will be used')

# dummy parameters
optP.add_option('--oldPrefix',action='store',dest='oldPrefix')
optP.add_option('--newPrefix',action='store',dest='newPrefix')
optP.add_option('--lfcHost',action='store',dest='lfcHost')
optP.add_option('--inputGUIDs',action='store',dest='inputGUIDs')
optP.add_option('--usePFCTurl',action='store',dest='usePFCTurl')

# get logger
tmpLog = PLogger.getPandaLogger()
tmpLog.info('start')

# parse options
options,args = optP.parse_args()
if options.verbose:
    tmpLog.debug("=== parameters ===")
    print options
    print

# save current dir
currentDir = os.getcwd()
currentDirFiles = os.listdir('.')
tmpLog.info("Running in %s " % currentDir)

# crate work dir
workDir = currentDir+"/workDir"
commands.getoutput('rm -rf %s' % workDir)
os.makedirs(workDir)
os.chdir(workDir)

# get run/event list
output = commands.getoutput('wget -h')
wgetCommand = 'wget'
for line in output.split('\n'):
    if re.search('--no-check-certificate',line) != None:
        wgetCommand = 'wget --no-check-certificate'
        break
com = '%s %s/cache/%s.gz' % (wgetCommand,
                             options.sourceURL,
                             options.goodRunListXML)
tmpLog.info("getting GRL with %s" % com)

nTry = 3
for iTry in range(nTry):
    print 'Try : %s' % iTry
    status,output = commands.getstatusoutput(com)
    print status,output
    if status == 0:
        break
    if iTry+1 == nTry:
        tmpLog.error("could not get GRL from panda server")
        sys.exit(EC_WGET)
    time.sleep(30)    
print commands.getoutput('gunzip %s.gz' % options.goodRunListXML)

# convert run/evt list to dataset/LFN list
try:
    status,epDs,epLFNs = PsubUtils.convertGoodRunListXMLtoDS(tmpLog,
                                                             options.goodRunListXML,
                                                             options.goodRunDataType,
                                                             options.goodRunProdStep,
                                                             options.goodRunListDS,
                                                             True)
    if not status:
        tmpLog.error("failed to convert GoodRunListXML")
        sys.exit(EC_GRL)
    if epDs == '':
        tmpLog.error("no datasets were extracted from AMI using %s" % options.goodRunListXML)
        sys.exit(EC_GRL)
    status = 0
except:
    errtype,errvalue = sys.exc_info()[:2]
    tmpLog.error("failed to convert GRL with %s %s" % (errtype,errvalue))
    sys.exit(EC_GRL)

print

tmpLog.debug("=== GRL output ===")
print epDs
print epLFNs
print

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

# go back to current dir
os.chdir(currentDir)

# write metadata.xml
metaDict = {}
metaDict['%%INDS%%'] = epDs
metaDict['%%INLFNLIST%%'] = epLFNs
metaFileName = 'metadata.xml'
commands.getoutput('rm -rf %s' % metaFileName)
mFH = open(metaFileName,'w')
import json
json.dump(metaDict,mFH)
mFH.close()

tmpLog.info('dump')
print commands.getoutput('pwd')
print commands.getoutput('ls -l')

# remove work dir
if not options.debug:
    commands.getoutput('rm -rf %s' % workDir)

# return
if status:
    tmpLog.error("execute script: Running script failed : StatusCode=%d" % status)
    sys.exit(status)
else:
    tmpLog.info("execute script: Running script was successful")
    sys.exit(0)
