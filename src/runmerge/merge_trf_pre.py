from RecExConfig.InputFilePeeker import inputFileSummary
from RecExConfig.RecoFunctions import ItemInListStartsWith
from AthenaCommon.Logging import logging

logPreInclude = logging.getLogger( 'MergePoolPreInclude' )

logPreInclude.info("=== Detecting Input File Format ===")

streamNames = []
try:
    streamNames = inputFileSummary['stream_names']
except KeyError:
    logPreInclude.warning('cannot find stream names - unable to determin POOL format, assuming format "AOD"')

logPreInclude.info('file_type   : %s' % inputFileSummary['file_type'])
logPreInclude.info('steam names : %s' % streamNames)

isAOD=True
isESD=False

## yes, always get inputs/output names from runArgs.xxxAODFile even though it has to be ESD file
inputs=runArgs.inputAODFile
output=runArgs.outputAODFile

if ItemInListStartsWith("StreamAOD"  ,streamNames) or \
   ItemInListStartsWith('StreamDAOD' ,streamNames) or \
   ItemInListStartsWith('StreamD2AOD',streamNames) or \
   ItemInListStartsWith('DAOD'       ,streamNames) or \
   ItemInListStartsWith('D2AOD'      ,streamNames):

    logPreInclude.info("Input AOD detected")

elif ItemInListStartsWith("StreamESD"  ,streamNames) or \
     ItemInListStartsWith('StreamDESD' ,streamNames) or \
     ItemInListStartsWith('StreamD2ESD',streamNames) or \
     ItemInListStartsWith('DESD'       ,streamNames) or \
     ItemInListStartsWith('D2ESD'      ,streamNames):

    logPreInclude.info("Input ESD detected")
    isAOD = False
    isESD = True

else:
    isAOD = False
    isESD = False
    raise RuntimeError("Cannot merge streamNames==%s"%streamNames)

## override the setting based on command-line arguments
logPreInclude.info("isAOD: %s isESD: %s" % (isAOD, isESD))

## unlock relevant JobProperties so that they can be changed.
rec.readAOD.unlock()
rec.readESD.unlock()
rec.doWriteAOD.unlock()
rec.doWriteESD.unlock()

athenaCommonFlags.PoolAODInput.unlock()
athenaCommonFlags.PoolAODOutput.unlock()
athenaCommonFlags.PoolESDInput.unlock()
athenaCommonFlags.PoolESDOutput.unlock()

## change and lock relevant JobProperties.
rec.readAOD.set_Value_and_Lock( isAOD )
rec.doWriteAOD.set_Value_and_Lock( isAOD )

rec.readESD.set_Value_and_Lock( isESD )
rec.doWriteESD.set_Value_and_Lock( isESD )

if isAOD:
    athenaCommonFlags.PoolAODInput.set_Value_and_Lock( inputs )
    athenaCommonFlags.PoolAODOutput.set_Value_and_Lock( output )
    athenaCommonFlags.PoolESDInput.set_Value_and_Lock( [] )
    athenaCommonFlags.PoolESDOutput.set_Value_and_Lock( '' )

elif isESD:
    athenaCommonFlags.PoolESDInput.set_Value_and_Lock( inputs )
    athenaCommonFlags.PoolESDOutput.set_Value_and_Lock( output )
    athenaCommonFlags.PoolAODInput.set_Value_and_Lock( [] )
    athenaCommonFlags.PoolAODOutput.set_Value_and_Lock( '' )
