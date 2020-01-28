import os
import os.path
import uuid
import subprocess
from pandawnutil.wnmisc.misc_utils import commands_get_status_output

if os.path.isabs(__file__):
    modFullName = __file__
else:
    modFullName = os.getcwd() + '/' + __file__
modFullPath = os.path.dirname(modFullName)    


class RunTracer:
    # constructor
    def __init__(self,debugFlag=False):
        self.wrapperName = 'wrapper'
        self.archOptMap  = {'m32':'lib','m64':'lib64'}
        self.libBaseDir  = None
        self.logName     = ''
        self.debugFlag   = debugFlag


    # make wrapper
    def make(self):
        print ("\n===== make PandaTracer =====")
        # create lib base dir
        if self.debugFlag:
            self.libBaseDir = os.getcwd()
        else:
            self.libBaseDir = os.getcwd() + '/' + str(uuid.uuid4())
            commands_get_status_output('rm -rf %s' % self.libBaseDir)
            os.makedirs(self.libBaseDir)
        # set output filename
        self.logName = self.libBaseDir + '/pandatracerlog.txt'
        outH = open('outfilename.h','w')
        outH.write('const char *pandatracer_outfilename = "%s";\n' % self.logName)
        outH.write("const char *pandatracer_sofilename = \"%s/$LIB/%s.so\";\n" % \
                   (self.libBaseDir,self.wrapperName))
        outH.close()
        # make lib and lib64
        for archOpt in self.archOptMap:
            archLib = self.archOptMap[archOpt]
            step1 = 'gcc -%s -I. -fPIC -c -Wall %s/%s.c -o %s.o' % \
                    (archOpt,modFullPath,self.wrapperName,self.wrapperName)
            step2 = 'gcc -%s -shared %s.o -ldl -lstdc++ -o %s/%s/%s.so' % \
                    (archOpt,self.wrapperName,self.libBaseDir,archLib,self.wrapperName)
            stepd = 'gcc -shared -fpic -o %s/%s/%s.so -xc /dev/null -%s' % \
                    (self.libBaseDir,archLib,self.wrapperName,archOpt)
            # makedir
            try:
                os.makedirs(self.libBaseDir+'/'+archLib)
            except:
                pass
            isFailed = False
            # make
            p = subprocess.Popen(step1.split(), stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE)
            out, err = p.communicate()
            if p.returncode != 0:
                print (" com : {0} failed with {1}".format(step1, err))
                isFailed = True
            else:
                p = subprocess.Popen(step2.split(), stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE)
                out, err = p.communicate()
                if p.returncode != 0:
                    print (" com : {0} failed with {1}".format(step2, err))
                    isFailed = True
            # make dummy if failed
            if isFailed:        
                print ("  %s failed" % archOpt)
                p = subprocess.Popen(stepd.split(), stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE)
                out, err = p.communicate()
                if p.returncode != 0:
                    print (" com : {0} failed with {1}".format(stepd, err))
                    print ("WARNING: %s is not supported" % archOpt)
                else:
                    print ("  %s uses dummy" % archOpt)
            else:
                print ("  %s succeeded" % archOpt)
        # log name
        commands_get_status_output('touch %s' % self.getLogName())
        print ("Log location -> %s" % self.getLogName())
        # return
        return

                                
    # get env var
    def getEnvVar(self):
        envStr  = ''
        envStr += "export PANDA_PRELOAD=%s/'$LIB'/%s.so${LD_PRELOAD:+:$LD_PRELOAD}; " % \
                  (self.libBaseDir,self.wrapperName)
        envStr += "export LD_PRELOAD=%s/'$LIB'/%s.so${LD_PRELOAD:+:$LD_PRELOAD}; " % \
                  (self.libBaseDir,self.wrapperName)
        return envStr


    # get log name
    def getLogName(self):
        return self.logName
