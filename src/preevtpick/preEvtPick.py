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
EC_EVP         = 147

# set TZ
os.environ['TZ'] = 'UTC'

optP = optparse.OptionParser(conflict_handler="resolve")
optP.add_option('-v', action='store_const', const=True, dest='verbose',  default=False,
                help='Verbose')
optP.add_option('-d', action='store_const', const=True, dest='debug',  default=False,
                help='Debug')
optP.add_option('--sourceURL',action='store',dest='sourceURL',default='',
                type='string', help='base URL where run/event list is retrived')
optP.add_option('--eventPickEvtList',action='store',dest='eventPickEvtList',default='',
                type='string', help='a file name which contains a list of runs/events for event picking')
optP.add_option('--eventPickDataType',action='store',dest='eventPickDataType',default='',
                type='string', help='type of data for event picking. one of AOD,ESD,RAW')
optP.add_option('--eventPickStreamName',action='store',dest='eventPickStreamName',default='',
                type='string', help='stream name for event picking. e.g., physics_CosmicCaloEM')
optP.add_option('--eventPickDS',action='store',dest='eventPickDS',default='',
                type='string', help='A comma-separated list of pattern strings. Datasets which are converted from the run/event list will be used when they match with one of the pattern strings. Either \ or "" is required when a wild-card is used. e.g., data\*')
optP.add_option('--eventPickStagedDS',action='store',dest='eventPickStagedDS',default='',
                type='string', help='--eventPick options create a temporary dataset to stage-in interesting files when those files are available only on TAPE, and then a stage-in request is automatically sent to DaTRI. Once DaTRI transfers the dataset to DISK you can use the dataset as an input using this option')
optP.add_option('--eventPickAmiTag',action='store',dest='eventPickAmiTag',default='',
                type='string', help='AMI tag used to match TAG collections names. This option is required when you are interested in older data than the latest one. Either \ or "" is required when a wild-card is used. e.g., f2\*')

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
                             options.eventPickEvtList)
tmpLog.info("getting run/event list with %s" % com)

nTry = 3
for iTry in range(nTry):
    print 'Try : %s' % iTry
    status,output = commands.getstatusoutput(com)
    print status,output
    if status == 0:
        break
    if iTry+1 == nTry:
        tmpLog.error("could not get run/event list from panda server")
        sys.exit(EC_WGET)
    time.sleep(30)    
print commands.getoutput('gunzip %s.gz' % options.eventPickEvtList)

# convert run/evt list to dataset/LFN list
try:
    epDs,epLFNs = PsubUtils.getDSsFilesByRunsEvents(workDir,
                                                    options.eventPickEvtList,
                                                    options.eventPickDataType,
                                                    options.eventPickStreamName,
                                                    tmpLog,
                                                    options.eventPickDS,
                                                    True,
                                                    options.eventPickAmiTag)
    # have to get new logger since DQ2 tweaks logger
    tmpLog = PLogger.getPandaLogger()
except:
    # have to get new logger since DQ2 tweaks logger
    tmpLog = PLogger.getPandaLogger()
    errtype,errvalue = sys.exc_info()[:2]
    tmpLog.error("failed to execute event picking with %s %s" % (errtype,errvalue))
    sys.exit(EC_EVP)

print

if options.verbose:
    tmpLog.debug("=== evp output ===")
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
