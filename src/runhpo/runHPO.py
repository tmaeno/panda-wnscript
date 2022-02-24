#!/bin/bash

"exec" "python" "-u" "$0" "$@"

import os
import re
import sys
import ast
import time
import getopt
import uuid
import json
import signal
import shutil
import xml.dom.minidom
try:
    import urllib.request as urllib
except ImportError:
    import urllib
from pandawnutil.wnmisc.misc_utils import commands_get_status_output, get_file_via_http, record_exec_directory, \
    get_hpo_sample, update_hpo_sample, update_events, CheckPointUploader, parse_harvester_events_json

# error code
EC_MissingArg  = 10
EC_NoInput     = 11
EC_Tarball     = 143
EC_WGET        = 146
EC_EVENT       = 147
EC_EXE_FAILED  = 150
EC_NOEVENT     = 160
EC_NOMOREEVENT = 161
EC_MAXLOOP     = 162

print ("=== start ===")
print (time.ctime())

debugFlag    = False
libraries    = ''
outputFile   = 'out.json'
inSampleFile = 'input_sample.json'
jobParams    = ''
inputFiles   = []
inputGUIDs   = []
runDir       = './'
oldPrefix    = ''
newPrefix    = ''
directIn     = False
usePFCTurl   = False
sourceURL    = 'https://gridui07.usatlas.bnl.gov:25443'
inMap        = {}
archiveJobO  = ''
writeInputToTxt = ''
scriptName = None
preprocess = False
postprocess = False
coprocess = False
outMetaFile = 'out_metadata.json'
outMetricsFile = None
pandaID = os.environ.get('PandaID')
if pandaID is None:
    pandaID = os.environ.get('PANDAID')
taskID = os.environ.get('PanDA_TaskID')
pandaURL = 'https://pandaserver.cern.ch:25443'
iddsURL = 'https://iddsserver.cern.ch:443'
dryRun = False
checkPointToSave = None
checkPointToLoad = None
checkPointInterval = 5
if 'PAYLOAD_OFFLINE_MODE' in os.environ:
    offlineMode = True
else:
    offlineMode = False
if 'PAYLOAD_TANDEM_MODE' in os.environ:
    tandemMode = True
else:
    tandemMode = False
localCheckPointFile = None
segmentID = None
maxLoopCount = None

# files for synchronization
sync_file_in = '__payload_in_sync_file__'
sync_file_out = '__payload_out_sync_file__'


# command-line parameters
opts, args = getopt.getopt(sys.argv[1:], "i:o:j:l:p:a:",
                           ["pilotpars", "debug", "oldPrefix=", "newPrefix=",
                            "directIn", "sourceURL=",
                            "pandaURL=", "iddsURL=",
                            "inputGUIDs=", "inMap=",
                            "usePFCTurl", "accessmode=",
                            "writeInputToTxt=",
                            "pandaID=", "taskID=",
                            "inSampleFile=", "outMetaFile=",
                            "outMetricsFile=", "dryRun",
                            "preprocess", "postprocess", "coprocess",
                            "checkPointToSave=", "checkPointToLoad=",
                            "checkPointInterval=", "segmentID=",
                            "maxLoopCount="
                            ])
for o, a in opts:
    if o == "-l":
        libraries = a
    if o == "-j":
        scriptName = a
    if o == "-p":
        jobParams = urllib.unquote(a)
    if o == "-i":
        inputFiles = ast.literal_eval(a)
    if o == "-o":
        outputFile = a
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
    if o == "--sourceURL":
        sourceURL = a
    if o == "--inMap":
        inMap = ast.literal_eval(a)
    if o == "-a":
        archiveJobO = a
    if o == "--usePFCTurl":
        usePFCTurl = True
    if o == "--writeInputToTxt":
        writeInputToTxt = a
    if o == "--preprocess":
        preprocess = True
    if o == "--postprocess":
        postprocess = True
    if o == "--coprocess":
        coprocess = True
    if o == '--pandaID':
        pandaID = int(a)
    if o == '--taskID':
        taskID = int(a)
    if o == '--pandaURL':
        pandaURL = a
    if o == '--iddsURL':
        iddsURL = a
    if o == '--inSampleFile':
        inSampleFile = a
    if o == '--outMetaFile':
        outMetaFile = a
    if o == '--outMetricsFile':
        outMetricsFile = a
    if o == '--dryRun':
        dryRun = True
    if o == '--checkPointToSave':
        checkPointToSave = a
    if o == '--checkPointToLoad':
        checkPointToLoad = a
    if o == '--checkPointInterval':
        checkPointInterval = int(a)
    if o == '--segmentID':
        segmentID = int(a)
    if o == '--maxLoopCount':
        maxLoopCount = int(a)

# dump parameter
try:
    print("=== parameters ===")
    print("PandaID", pandaID)
    print("taskID", taskID)
    print("segmentID", segmentID)
    print("libraries", libraries)
    print("runDir", runDir)
    print("jobParams", jobParams)
    print("inputFiles", inputFiles)
    print("scriptName", scriptName)
    print("outputFile", outputFile)
    print("inputGUIDs", inputGUIDs)
    print("oldPrefix", oldPrefix)
    print("newPrefix", newPrefix)
    print("directIn", directIn)
    print("usePFCTurl", usePFCTurl)
    print("debugFlag", debugFlag)
    print("sourceURL", sourceURL)
    print("inMap", inMap)
    print("archiveJobO", archiveJobO)
    print("writeInputToTxt", writeInputToTxt)
    print("preprocess", preprocess)
    print("postprocess", postprocess)
    print("pandaURL", pandaURL)
    print("iddsURL", iddsURL)
    print("inSampleFile", inSampleFile)
    print("outMetaFile", outMetaFile)
    print("outMetricsFile", outMetricsFile)
    print("dryRun", dryRun)
    print("checkPointToSave", checkPointToSave)
    print("checkPointToLoad", checkPointToLoad)
    print("checkPointInterval", checkPointInterval)
    print("offlineMode", offlineMode)
    print("maxLoopCount", maxLoopCount)
    print("===================\n")
except Exception as e:
    print('ERROR : missing parameters : %s' % str(e))
    sys.exit(EC_MissingArg)

# save current dir
currentDir = record_exec_directory()
currentDirFiles = os.listdir('.')

# pilot iteration count
if 'PILOT_EXEC_ITERATION_COUNT' in os.environ:
    iterationCount = os.environ['PILOT_EXEC_ITERATION_COUNT']
else:
    iterationCount = None

# wait until the sync file is created by the main exec
if postprocess:
    file_to_check = os.path.join(currentDir, sync_file_out)
    if tandemMode:
        print('waiting until the main exec is done')
        while not os.path.exists(file_to_check):
            time.sleep(10)
    # remove sync files for subsequent execution
    if os.path.exists(file_to_check):
        os.remove(file_to_check)
    if os.path.exists(os.path.join(currentDir, sync_file_in)):
        os.remove(os.path.join(currentDir, sync_file_in))

# work dir
workDir = currentDir+"/workDir"

# for input
directTmpTurl = {}
directPFNs = {}
if not postprocess and not coprocess:
    # check loop count
    if maxLoopCount and iterationCount:
        if maxLoopCount <= int(iterationCount):
            print("INFO : exit since loop count PILOT_EXEC_ITERATION_COUNT={} reached the limit".format(iterationCount))
            sys.exit(EC_MAXLOOP)
    # create work dir
    commands_get_status_output('rm -rf %s' % workDir)
    os.makedirs(workDir)

    # collect GUIDs from PoolFileCatalog
    try:
        print ("\n===== PFC from pilot =====")
        tmpPcFile = open("PoolFileCatalog.xml")
        print (tmpPcFile.read())
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
            # LFN
            lfn = pfn.split('/')[-1]
            lfn = re.sub('\?GoogleAccessId.*$','', lfn)
            lfn = re.sub('\?X-Amz-Algorithm.*$', '', lfn)
            # append
            directTmpTurl[id] = pfn
            directPFNs[lfn] = pfn
    except Exception as e:
        print ('ERROR : Failed to collect GUIDs : %s' % str(e))

    # add secondary files if missing
    for tmpToken in inMap:
        tmpList = inMap[tmpToken]
        for inputFile in tmpList:
            if not inputFile in inputFiles:
                inputFiles.append(inputFile)
    print ('')
    print ("===== inputFiles with inMap =====")
    print ("inputFiles",inputFiles)
    print ('')

# move to work dir
os.chdir(workDir)

# preprocess or single-step execution
if not postprocess and not coprocess:
    # expand libraries
    if libraries == '':
        tmpStat, tmpOut = 0, ''
    elif libraries.startswith('/'):
        tmpStat, tmpOut = commands_get_status_output('tar xvfzm %s' % libraries)
        print (tmpOut)
    else:
        tmpStat, tmpOut = commands_get_status_output('tar xvfzm %s/%s' % (currentDir,libraries))
        print (tmpOut)
    if tmpStat != 0:
        print ("ERROR : {0} is corrupted".format(libraries))
        sys.exit(EC_Tarball)

    # expand jobOs if needed
    if archiveJobO != "" and libraries == '':
        url = '%s/cache/%s' % (sourceURL, archiveJobO)
        tmpStat, tmpOut = get_file_via_http(full_url=url)
        if not tmpStat:
            print ("ERROR : " + tmpOut)
            sys.exit(EC_WGET)
        tmpStat, tmpOut = commands_get_status_output('tar xvfzm %s' % archiveJobO)
        print (tmpOut)
        if tmpStat != 0:
            print ("ERROR : {0} is corrupted".format(archiveJobO))
            sys.exit(EC_Tarball)

# make run dir just in case
commands_get_status_output('mkdir %s' % runDir)
# go to run dir
os.chdir(runDir)

# preprocess or single-step execution
eventFileName = '__panda_events.json'
sampleFileName = '__hpo_sample.txt'
eventStatusDumpFile = os.path.join(currentDir, 'event_status.dump')
if 'X509_USER_PROXY' in os.environ:
    certfile = os.environ['X509_USER_PROXY']
else:
    certfile = '/tmp/x509up_u{0}'.format(os.getuid())
keyfile = certfile
if not postprocess and not coprocess:
    commands_get_status_output('rm -rf {0}'.format(eventFileName))
    commands_get_status_output('rm -rf {0}'.format(sampleFileName))
    # check input files
    inputFileMap = {}
    if inputFiles != []:
        print ("=== check input files ===")
        newInputs = []
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
                    os.symlink(os.path.relpath(os.path.join(currentDir, inputFile), os.getcwd()), inputFile)
                    newInputs.append(inputFile)
                    foundFlag = True
                    inputFileMap[inputFile] = inputFile
            if not foundFlag:
                print ("%s not exist" % inputFile)
        inputFiles = newInputs
        if len(inputFiles) == 0:
            print ("ERROR : No input file is available")
            sys.exit(EC_NoInput)
        print ("=== New inputFiles ===")
        print (inputFiles)

    # add current dir to PATH
    os.environ['PATH'] = '.:'+os.environ['PATH']

    print ("\n=== ls in run dir : %s (%s) ===" % (runDir, os.getcwd()))
    print (commands_get_status_output('ls -l')[-1])
    print ('')

    # chmod +x just in case
    commands_get_status_output('chmod +x %s' % scriptName)
    if scriptName == '':
        commands_get_status_output('chmod +x %s' % jobParams.split()[0])

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
            print ("=== write input to file ===")
        if inMap == {}:
            inStr = ','.join(inputFiles)
            # replace
            newJobParams = newJobParams.replace('%IN',inStr)
            # write to file
            tmpKeyName = 'IN'
            if tmpKeyName in writeInputToTxtMap:
                commands_get_status_output('rm -f %s' % writeInputToTxtMap[tmpKeyName])
                with open(writeInputToTxtMap[tmpKeyName],'w') as f:
                    json.dump(inputFiles, f)
                print ("%s to %s : %s" % (tmpKeyName, writeInputToTxtMap[tmpKeyName], str(inputFiles)))
        else:
            # multiple inputs
            for tmpToken in inMap:
                tmpList = inMap[tmpToken]
                inStr = ','.join(tmpList) + ' '
                # replace
                newJobParams = re.sub('%'+tmpToken+'(?P<sname> |$|\"|\')',inStr+'\g<sname>',newJobParams)
                # write to file
                tmpKeyName = tmpToken
                if tmpKeyName in writeInputToTxtMap:
                    commands_get_status_output('rm -f %s' % writeInputToTxtMap[tmpKeyName])
                    with open(writeInputToTxtMap[tmpKeyName], 'w') as f:
                        json.dump(tmpList, f)
                    print ("%s to %s : %s" % (tmpKeyName, writeInputToTxtMap[tmpKeyName], str(tmpList)))
        if writeInputToTxtMap != {}:
            print ('')
    # fetch an event
    print ("=== getting events ===\n")
    for iii in range(10):
        if dryRun:
            sample_id = 123
            event_id = '{0}-{1}-0-{2}-5'.format(taskID, pandaID, sample_id)
            with open(sampleFileName, 'w') as f:
                f.write('{0},{1}'.format(event_id, sample_id))
            break
        if not offlineMode:
            print ("from PanDA")
            # get events from panda server
            data = dict()
            data['pandaID'] = pandaID
            data['jobsetID'] = 0
            data['taskID'] = taskID
            data['nRanges'] = 1
            if segmentID is not None:
                data['segment_id'] = segmentID
            url = pandaURL + '/server/panda/getEventRanges'
            tmpStat, tmpOut = get_file_via_http(file_name=eventFileName, full_url=url, data=data,
                                                headers={'Accept': 'application/json'},
                                                certfile=certfile, keyfile=keyfile)
        else:
            # parse harvester json to get events
            print ("from json")
            tmpStat, tmpOut = parse_harvester_events_json(pandaID, 'JobsEventRanges.json', eventFileName)
        if not tmpStat:
            print ("ERROR : " + tmpOut)
            sys.exit(EC_WGET)
        with open(eventFileName) as f:
            print(f.read())
        print ('')
        # convert to dict
        try:
            with open(eventFileName) as f:
                event_dict = json.load(f)
                # no events
                if not event_dict['eventRanges']:
                    break
                event = event_dict['eventRanges'][0]
                event_id = event['eventRangeID']
                sample_id = event_id.split('-')[3]
                print (" got eventID={0} sampleID={1}\n".format(event_id, sample_id))
                if taskID is None:
                    taskID = event_id.split('-')[0]
                    print (" set eventID={0} from None\n".format(taskID))
                # check with iDDS
                if not offlineMode:
                    print ("\n=== getting HP samples from iDDS ===")
                    tmpStat, tmpOut = get_hpo_sample(iddsURL, taskID, sample_id, certfile, keyfile)
                else:
                    print ("\n=== getting HP samples from json ===")
                    tmpStat, tmpOut = True, event['hp_point']
                    if 'checkpoint' in event:
                        localCheckPointFile = event['checkpoint']
                if not tmpStat:
                    raise RuntimeError(tmpOut)
                print ("\n got {0}".format(str(tmpOut)))
                if tmpOut['loss'] is not None:
                    print ("\n already evaluated")
                    print ("\n=== updating events in PanDA ===")
                    update_events(pandaURL, event_id, 'finished', certfile, keyfile)
                    print ('')
                else:
                    print ("\n to evaluate")
                    with open(sampleFileName, 'w') as wf:
                        wf.write('{0},{1}'.format(event_id, sample_id))
                    with open(inSampleFile, 'w') as wf:
                        json.dump(tmpOut['parameters'], wf)
                    break
        except RuntimeError as e:
            print ("ERROR: failed to get a HP sample from iDDS. {0}".format(str(e)))
        except Exception as e:
            print ("ERROR: failed to get an event from PanDA. {0}".format(str(e)))
            sys.exit(EC_EVENT)
    # no event
    if not os.path.exists(sampleFileName):
        print ("\n==== Result ====")
        if iterationCount is None or int(iterationCount) == 0:
            print ("INFO : exit due to no event available")
            sys.exit(EC_NOEVENT)
        print("INFO : exit due to no more event available")
        sys.exit(EC_NOEVENT)
        #sys.exit(EC_NOMOREEVENT)

    # get checkpoint file
    if checkPointToSave is not None:
        print ("\n=== getting checkpoint ===")
        if not offlineMode:
            cpFile = 'hpo_cp_{0}_{1}'.format(taskID, sample_id)
            url = '%s/cache/%s' % (sourceURL, cpFile)
            tmpStat, tmpOut = get_file_via_http(full_url=url)
        else:
            if localCheckPointFile is None:
                tmpStat, tmpOut = False, ''
            else:
                print ('using local file : {0}'.format(localCheckPointFile))
                cpFile = localCheckPointFile
                tmpStat, tmpOut = True, ''
        if not tmpStat:
            print ("checkpoint file unavailable : " + tmpOut)
        else:
            if checkPointToLoad is None:
                tmpStat, tmpOut = commands_get_status_output('tar xvfzm %s' % cpFile)
                print (tmpOut)
            else:
                shutil.move(cpFile, checkPointToLoad)
        print ('')

    # construct command
    com = ''
    if preprocess:
        tmpTrfName = os.path.join(currentDir, '__run_main_exec.sh')
    else:
        tmpTrfName = 'trf.%s.py' % str(uuid.uuid4())
    tmpTrfFile = open(tmpTrfName,'w')
    if preprocess:
        tmpTrfFile.write('cd {0}\n'.format(os.path.relpath(os.getcwd(), currentDir)))
        tmpTrfFile.write('export PATH=$PATH:.\n')
        tmpTrfFile.write('{0} {1}\n'.format(scriptName,newJobParams))
    else:
        # wrap commands to invoke execve even if preload is removed/changed
        tmpTrfFile.write('import os,sys\nstatus=os.system(r"""%s %s""")\n' % (scriptName,newJobParams))
        tmpTrfFile.write('status %= 255\nsys.exit(status)\n\n')
    tmpTrfFile.close()

    # make sync file
    with open(os.path.join(currentDir, sync_file_in), 'w') as f:
        pass

    # return if preprocess
    if preprocess:
        commands_get_status_output('chmod +x {0}'.format(tmpTrfName))
        print ("\n==== Result ====")
        print ("prepossessing successfully done")
        print ("INFO : produced {0}".format(tmpTrfName))
        sys.exit(0)

    com += 'cat %s;python -u %s' % (tmpTrfName,tmpTrfName)

    # temporary output to avoid MemeoryError
    tmpOutput = 'tmp.stdout.%s' % str(uuid.uuid4())
    tmpStderr = 'tmp.stderr.%s' % str(uuid.uuid4())

# read back event id and sample id
with open(sampleFileName) as f:
    tmp_str = f.read()
    event_id, sample_id = tmp_str.split(',')

if not postprocess:
    # run checkpoint uploader
    cup = None
    if checkPointToSave is not None:
        cup = CheckPointUploader(taskID, pandaID, sample_id, checkPointToSave, checkPointInterval,
                                 sourceURL, certfile, keyfile, debugFlag, offlineMode,
                                 eventStatusDumpFile)
        cup.start()
    if coprocess:
        signal.pause()

    print ("\n=== execute ===")
    print (com)
    # run athena
    if not debugFlag:
        # write stdout to tmp file
        com += ' > %s 2> %s' % (tmpOutput,tmpStderr)
        status,out = commands_get_status_output(com)
        print (out)
        status %= 255
        try:
            tmpOutFile = open(tmpOutput)
            for line in tmpOutFile:
                print (line[:-1])
            tmpOutFile.close()
        except:
            pass
        try:
            stderrSection = True
            tmpErrFile = open(tmpStderr)
            for line in tmpErrFile:
                if stderrSection:
                    stderrSection = False
                    print ("\n=== stderr ===")
                print (line[:-1])
            tmpErrFile.close()
        except:
            pass
        # print 'sh: line 1:  8278 Aborted'
        try:
            if status != 0:
                print (out.split('\n')[-1])
        except:
            pass
    else:
        status = os.system(com)

    # terminate checkpoint uploader
    if cup is not None:
        cup.terminate()
        if status == 0:
            cup.cleanup()
else:
    # no event
    if not os.path.exists(sampleFileName):
        print ("\n==== Result ====")
        print ("INFO : exit due to no event")
        sys.exit(0)
    # set 0 for postprocess
    status = 0

print ('')
print ("=== ls in run dir : {0} ({1}) ===".format(runDir, os.getcwd()))
print (commands_get_status_output('ls -l')[-1])
print ('')

# get loss
print ("=== getting loss from {0} ===".format(outputFile))
loss = None
if not os.path.exists(outputFile):
    print ("ERROR: {0} doesn't exist".format(outputFile))
    status = EC_EXE_FAILED
else:
    with open(outputFile) as f:
        try:
            print (f.read())
            f.seek(0)
            out_dict = json.load(f)
            if 'status' not in out_dict or out_dict['status'] == 0:
                loss = out_dict['loss']
                print ("got loss={0}".format(loss))
            else:
                tmpStr = "ERROR: failed to evaluate. status={0}".format(out_dict['status'])
                if 'message' in out_dict:
                    tmpStr = tmpStr + ' message={0}'.format(out_dict['message'])
                print (tmpStr)
        except Exception as e:
            print ("ERROR: failed to get loss. {0}".format(str(e)))
    # copy results
    commands_get_status_output('mv %s %s' % (outputFile, currentDir))
print ('')

# report loss
if loss is not None and not dryRun:
    if not offlineMode:
        print ("=== reporting loss to iDDS ===")
        tmpStat, tmpOut = update_hpo_sample(iddsURL, taskID, sample_id, loss, certfile, keyfile)
        if not tmpStat:
            print ('ERROR: {0}\n'.format(tmpOut))
        else:
            print ("\n=== updating events in PanDA ===")
            update_events(pandaURL, event_id, 'finished', certfile, keyfile)
            print ('')
    else:
        print ("=== dump loss + event ===")
        with open(eventStatusDumpFile, 'w') as f:
            data = {str(pandaID): [{'eventRangeID': event_id, 'eventStatus': 'finished', 'loss': loss}]}
            json.dump(data, f)
            print (data)

# copy old jobReport
if iterationCount is not None:
    commands_get_status_output('cp {} .'.format(os.path.join(currentDir, 'jobReport.json')))

# add user job metadata
try:
    from pandawnutil.wnmisc import misc_utils
    misc_utils.add_user_job_metadata(outMetaFile)
except Exception:
    print ("WARNING: user metadata {} is corrupted".format(outMetaFile))

# metrics
if outMetricsFile is not None:
    newName, oldName = outMetricsFile.split('^')
    if iterationCount is not None:
        newName = "{}_{}".format(newName, iterationCount)
    tmpOldName = "%s_%s" % (oldName, sample_id)
    tmpStat, tmpOut = commands_get_status_output('mv {0} {1}; tar cvfz {2}/{3} {1}'.format(oldName, tmpOldName,
                                                                                           currentDir, newName))
    # make job report
    if tmpStat == 0:
        if os.path.exists('jobReport.json'):
            with open('jobReport.json') as f:
                job_report = json.load(f)
        else:
            job_report = {}
        job_report.setdefault("files", {})
        job_report["files"].setdefault("output", [])
        job_report["files"]["output"].append({"subFiles": [
            {
                "file_guid": str(uuid.uuid4()),
                "file_size": os.stat(os.path.join(currentDir, newName)).st_size,
                "name": newName,
                "nentries": 1,
            }
        ]})
        with open('jobReport.json', 'w') as f:
            json.dump(job_report, f)

# create empty PoolFileCatalog.xml if it doesn't exist
pfcName = 'PoolFileCatalog.xml'
pfcSt,pfcOut = commands_get_status_output('ls %s' % pfcName)
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
commands_get_status_output('mv %s %s' % (pfcName,currentDir))

# copy useful files
for patt in ['runargs.*','runwrapper.*','jobReport.json','log.*']:
    commands_get_status_output('mv -f %s %s' % (patt,currentDir))

# go back to current dir
os.chdir(currentDir)

print ("\n=== ls in entry dir : %s ===" % os.getcwd())
print (commands_get_status_output('ls -l')[-1])

# remove work dir
if not debugFlag:
    commands_get_status_output('rm -rf %s' % workDir)

# return
print ("\n==== Result ====")
if status:
    print ("ERROR : execute script: Running script failed : StatusCode=%d" % status)
    sys.exit(status)
else:
    print ("INFO : execute script: Running script was successful")
    sys.exit(0)
