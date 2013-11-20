import sys
import logging

rootLog = None

# set logger
def setLogger(tmpLog):
    global rootLog
    rootLog = tmpLog


# return logger
def getPandaLogger():
    # use root logger
    global rootLog
    if rootLog == None:
        rootLog = logging.getLogger('')
    # add StreamHandler if no handler
    if rootLog.handlers == []:
        rootLog.setLevel(logging.DEBUG)
        console = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
        #formatter = logging.Formatter('%(levelname)s : %(message)s')
        console.setFormatter(formatter)
        rootLog.addHandler(console)
    # return
    return rootLog


# reset logger
def resetLogger():
    logging.shutdown()
    reload(logging)
    setLogger(None)
    return getPandaLogger()
