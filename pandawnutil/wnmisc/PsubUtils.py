import re
import sys
from pandawnutil.wnlogger import PLogger

EC_Failed = 255
EC_Config = 100


# list datasets by GUIDs
def listDatasetsByGUIDs(guids,dsFilter,tmpLog,verbose=False,forColl=False):
    # DQ2 API
    try:
        from dq2.clientapi.DQ2 import DQ2
        # have to reset logger since DQ2 tweaks logger
        tmpLog = PLogger.resetLogger()
        dq2 = DQ2()
        dq2.listDatasetsByGUIDs(guids) 
    except:
        errtype,errvalue = sys.exc_info()[:2]
        errStr = "dq2.listDatasetsByGUIDs failed with %s:%s" % (errtype,
                                                                errvalue)
        tmpLog.error(errStr)
        sys.exit(EC_Failed)

    # get filter
    dsFilters = []
    if dsFilter != '':
        dsFilters = dsFilter.split(',')
    retMap = {}
    allMap = {}
    iLookUp = 0
    guidLfnMap = {}
    checkedDSList = []
    # loop over all GUIDs
    for guid in guids:
        # check existing map to avid redundant lookup
        if guidLfnMap.has_key(guid):
            retMap[guid] = guidLfnMap[guid]
            continue
        tmpLog.debug('getting datasetname from ddm for %s' % guid)
        iLookUp += 1
        if iLookUp % 20 == 0:
            time.sleep(1)
        # get datasets
        outMap = dq2.listDatasetsByGUIDs([guid])
        tmpLog.debug(outMap)
        # datasets are deleted
        if outMap == {}:
            allMap[guid] = []
            continue
        # check with filter
        tmpDsNames = []
        tmpAllDsNames = []
        for tmpDsName in outMap.values()[0]:
            # ignore junk datasets
            if tmpDsName.startswith('panda') or \
                   tmpDsName.startswith('user') or \
                   tmpDsName.startswith('group') or \
                   re.search('_sub\d+$',tmpDsName) != None or \
                   re.search('_dis\d+$',tmpDsName) != None or \
                   re.search('_shadow$',tmpDsName) != None:
                continue
            tmpAllDsNames.append(tmpDsName)
            # check with filter            
            if dsFilters != []:
                flagMatch = False
                for tmpFilter in dsFilters:
                    # replace . to \.                    
                    tmpFilter = tmpFilter.replace('.','\.')                    
                    # replace * to .*
                    tmpFilter = tmpFilter.replace('*','.*')
                    if re.search('^'+tmpFilter,tmpDsName) != None:
                        flagMatch = True
                        break
                # not match
                if not flagMatch:
                    continue
            # append    
            tmpDsNames.append(tmpDsName)
        # empty
        if tmpDsNames == []:
            # there may be multiple GUIDs for the same event, and some may be filtered by --eventPickDS
            allMap[guid] = tmpAllDsNames
            continue
        # duplicated
        if len(tmpDsNames) != 1:
            if not forColl:
                errStr = "there are multiple datasets %s for GUID:%s. Please set --eventPickDS and/or --eventPickStreamName to choose one dataset"\
                         % (str(tmpAllDsNames),guid)
            else:
                errStr = "there are multiple datasets %s for GUID:%s. Please set --eventPickDS to choose one dataset"\
                         % (str(tmpAllDsNames),guid)
            tmpLog.error(errStr)
            sys.exit(EC_Failed)
        # get LFN
        if not tmpDsNames[0] in checkedDSList:
            tmpMap,tmpStat = dq2.listFilesInDataset(tmpDsNames[0],verbose)
            for tmpGUID,tmpVal in tmpMap.iteritems():
                guidLfnMap[tmpGUID] = (tmpDsNames[0],tmpVal['lfn'])
            checkedDSList.append(tmpDsNames[0])
        # append
        if not guidLfnMap.has_key(guid):
            errStr = "LFN for %s in not found in %s" % (guid,tmpDsNames[0])
            tmpLog.error(errStr)
            sys.exit(EC_Failed)
        retMap[guid] = guidLfnMap[guid]
    # return
    return retMap,allMap



# get list of datasets and files by list of runs/events
def getDSsFilesByRunsEvents(curDir,runEventTxt,dsType,streamName,tmpLog,dsPatt='',verbose=False,amiTag=""):
    # set 
    from eventLookupClient import eventLookupClient
    elssiIF = eventLookupClient()
    elssiIF.debug = verbose
    # open run/event txt
    if '/' in runEventTxt:
        tmpLog.error('%s must be in the current directory' % runEventTxt.split('/')[-1])
        sys.exit(EC_Config)
    runevttxt = open('%s/%s' % (curDir,runEventTxt))
    # convert dsType to Athena stream ref
    if dsType == 'AOD':
        streamRef = 'StreamAOD_ref'
    elif dsType == 'ESD':
        streamRef = 'StreamESD_ref'
    elif dsType == 'RAW':
        streamRef = 'StreamRAW_ref'
    else:
        errStr  = 'invalid data type %s for event picking. ' % dsType
        errStr += ' Must be one of AOD,ESD,RAW'
        tmpLog.error(errStr)
        sys.exit(EC_Config)
    tmpLog.info('getting dataset names and LFNs from Event Lookup service')
    # read
    runEvtList = []
    guids = []
    guidRunEvtMap = {}
    runEvtGuidMap = {}    
    for line in runevttxt:
        items = line.split()
        if len(items) != 2:
            continue
        runNr,evtNr = items
        runEvtList.append([runNr,evtNr])
    # close
    runevttxt.close()
    # bulk lookup
    nEventsPerLoop = 500
    iEventsTotal = 0
    while iEventsTotal < len(runEvtList):
        tmpRunEvtList = runEvtList[iEventsTotal:iEventsTotal+nEventsPerLoop]
        iEventsTotal += nEventsPerLoop
        for tmpItem in tmpRunEvtList:
            sys.stdout.write('.')
        sys.stdout.flush()
        # check with ELSSI
        if streamName == '':
            guidListELSSI = elssiIF.doLookup(tmpRunEvtList,tokens=streamRef,
                                             amitag=amiTag,extract=True)
        else:
            guidListELSSI = elssiIF.doLookup(tmpRunEvtList,stream=streamName,tokens=streamRef,
                                             amitag=amiTag,extract=True)
        if guidListELSSI == None or len(guidListELSSI) == 0:
            if not verbose:
                print
            errStr = ''    
            for tmpLine in elssiIF.output:
                errStr += tmpLine + '\n'
            tmpLog.error(errStr)    
            errStr = "failed to get GUID from Event Lookup service"
            tmpLog.error(errStr)
            sys.exit(EC_Config)
        if verbose:
            print guidListELSSI
        # check attribute
        attrNames, attrVals = guidListELSSI
        def getAttributeIndex(attr):
            for tmpIdx,tmpAttrName in enumerate(attrNames):
                if tmpAttrName.strip() == attr:
                    return tmpIdx
            tmpLog.error("cannot find attribute=%s in %s provided by Event Lookup service" % \
                         (attr,str(attrNames)))
            sys.exit(EC_Config)
        # get index
        indexEvt = getAttributeIndex('EventNumber')
        indexRun = getAttributeIndex('RunNumber')
        indexTag = getAttributeIndex(streamRef)
        # check events
        for runNr,evtNr in tmpRunEvtList:
            paramStr = 'Run:%s Evt:%s Stream:%s' % (runNr,evtNr,streamName)
            if verbose:
                tmpLog.debug(paramStr)
            # collect GUIDs    
            tmpguids = []
            for attrVal in attrVals:
                if runNr == attrVal[indexRun] and evtNr == attrVal[indexEvt]:
                    tmpGuid = attrVal[indexTag]
                    # check non existing
                    if tmpGuid == 'NOATTRIB':
                        continue
                    if not tmpGuid in tmpguids:
                        tmpguids.append(tmpGuid)
            # not found            
            if tmpguids == []:
                if not verbose:
                    print
                errStr = "no GUIDs were found in Event Lookup service for %s" % paramStr
                tmpLog.error(errStr)
                sys.exit(EC_Config)
            # append
            for tmpguid in tmpguids:
                if not tmpguid in guids:
                    guids.append(tmpguid)
                    guidRunEvtMap[tmpguid] = []
                guidRunEvtMap[tmpguid].append((runNr,evtNr))
            runEvtGuidMap[(runNr,evtNr)] = tmpguids
            if verbose:
                tmpLog.debug("   GUID:%s" % str(tmpguids))
    if not verbose:
        print
    # convert to dataset names and LFNs
    dsLFNs,allDSMap = listDatasetsByGUIDs(guids,dsPatt,tmpLog,verbose)
    if verbose:
        tmpLog.debug(dsLFNs)
    # check duplication
    for runNr,evtNr in runEvtGuidMap.keys():
        tmpLFNs = []
        tmpAllDSs = {}
        for tmpguid in runEvtGuidMap[(runNr,evtNr)]:
            if dsLFNs.has_key(tmpguid):
                tmpLFNs.append(dsLFNs[tmpguid])
            else:
                tmpAllDSs[tmpguid] = allDSMap[tmpguid]
                if guidRunEvtMap.has_key(tmpguid):
                    del guidRunEvtMap[tmpguid]
        # empty        
        if tmpLFNs == []:
            paramStr = 'Run:%s Evt:%s Stream:%s' % (runNr,evtNr,streamName)                        
            errStr = "--eventPickDS='%s' didn't pick up a file for %s\n" % (dsPatt,paramStr)
            for tmpguid,tmpAllDS in tmpAllDSs.iteritems():
                errStr += "    GUID:%s dataset:%s\n" % (tmpguid,str(tmpAllDS))
            tmpLog.error(errStr)
            sys.exit(EC_Config)
        # duplicated    
        if len(tmpLFNs) != 1:
            paramStr = 'Run:%s Evt:%s Stream:%s' % (runNr,evtNr,streamName)            
            errStr = "multiple LFNs %s were found in ELSSI for %s. " % (str(tmpLFNs),paramStr)
            errStr += "Please set --eventPickDS and/or --eventPickStreamName and/or --eventPickAmiTag correctly"
            tmpLog.error(errStr)
            sys.exit(EC_Config)
    if verbose:
        tmpLog.debug("Got")
        print dsLFNs
    # change to dataset and file map 
    inDS = ''
    filelist = []
    tmpDsNameList = []
    tmpLFNList = []
    for tmpGUID,tmpDsLFNs in dsLFNs.iteritems():
        tmpDsName,tmpLFN = tmpDsLFNs
        # set filelist
        if not tmpLFN in tmpLFNList:
            tmpLFNList.append(tmpLFN)
            filelist.append({'lfn':tmpLFN})
        # set inDS    
        if not tmpDsName in tmpDsNameList:
            tmpDsNameList.append(tmpDsName)
            inDS += '%s,' % tmpDsName
    inDS = inDS[:-1]
    # return
    return inDS,filelist
