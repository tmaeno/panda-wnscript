#!/usr/bin/env python
###################################################
#  wrapper script to merge ROOT files using hadd
###################################################
import getopt
import sys
import os
import tempfile

def __usage__():
    '''
    hadd wrapper

    Usage:

    $ hadd_merger.py -i %IN -o %OUT -a '<hadd arguments>' 
    '''

    sys.stdout.write(__usage__.__doc__ + '\n')

## system command executor with subprocess
def execSyscmdSubprocess(cmd, wdir=os.getcwd()):

    import subprocess
    import shlex
    import time

    exitcode = 0

    child  = 0
    fdout = -1
    fderr = -1

    stdout = ''
    stderr = ''

    try:
        child = subprocess.Popen(cmd, cwd=wdir, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True)

        fdout = child.stdout
        fderr = child.stderr

        while 1:
            exitcode = child.poll()
            if exitcode is not None:
                break
            else:
                time.sleep(0.3)
    finally:

        if child:

            for l in fdout:
                stdout += l

            for l in fderr:
                stderr += l

    return (exitcode, stdout, stderr)

def __parse_arguments__(argv):
    ''' parsing command-line argument '''
    opts, args = getopt.getopt(argv, "i:o:a:n:",
                               ["inputs=","output=","args_hadd=","maxinputs="])

    inputs    = []
    output    = ''
    hadd_args = '-n 10'
    maxinputs = 5

    for o,a in opts:
        if o in ['-i','--inputs']:
            inputs = a.split(',')
        if o in ['-o','--output']:
            output = a
        if o in ['-n', '--maxinputs']:
            maxinputs = int(a)
        if o in ['-a','--args_hadd']:
            hadd_args = a
#            largs = a.split(' ')
#            if largs.count('-n') > 0:  ## -n option already specified by user
#                hadd_args = a
#            else:
#                hadd_args = '%s -n 10' % a

    if not inputs or not output:
        raise getopt.GetoptError('Unknown Inputs or Output')

    return (inputs, output, maxinputs, hadd_args)

if __name__ == "__main__":

    rc = 0
    doMerge = True

    #####
    #  - split the input sources into chunks of "maxinputs".
    #  - merge each chunk and produce a intermediate file.
    #  - the intermediate files form a new list of input sources that are split again into chunks of "maxinputs".
    #  - iterate the splitting, merging until there is only one intermediate file.
    #  - rename the intermediate file to the final output filename.
    try:
        ## resolving hadd options
        (inputs, output, maxinputs, hadd_args ) = __parse_arguments__( sys.argv[1:] )

        chunks = [inputs[i:i+maxinputs] for i in range(0,len(inputs),maxinputs)]

        ## no need to merge if there is only 1 input file
        if len(inputs) == 1:
            doMerge = False

        while doMerge:
            tmp_outputs = []
            for c in chunks:
                fid, tmp_out = tempfile.mkstemp(prefix='_merge_', suffix='.root', dir=os.getcwd())
                cmd = 'hadd %s %s %s' % ( hadd_args, tmp_out, ' '.join( c ) )
                #cmd = 'cat %s > %s' % ( ' '.join( c ), tmp_out )
                
                print ('merging "%s" ==> %s' % ( ','.join( c ), tmp_out ))

                (rc,out,err) = execSyscmdSubprocess( '%s' % cmd )

                print (out)
                print (err)

                if rc != 0:
                    break
                else:
                    tmp_outputs.append( tmp_out )
                    ## merge output is ready, remove the input files of this merge
                    for f in c:
                        os.unlink( f )

            if rc != 0:
                ## something wrong with the merging, stop the job and report error
                chunks  = []
                doMerge = False
            else:
                chunks = [tmp_outputs[i:i+maxinputs] for i in range(0,len(tmp_outputs),maxinputs)]
                if len(tmp_outputs) == 1:
                    ## the final merged file is produced
                    doMerge = False

        if rc == 0:
            if len(chunks) == 1 and len(chunks[0]) == 1 and os.path.exists( chunks[0][0] ):
                ## everything looks ok, move the final output to the
                os.rename( chunks[0][0], output)
            else:
                raise Exception('merge output %s not produced properly' % chunks[0][0])
 
        sys.exit(rc)
        
    except getopt.GetoptError as e:
        print (str(e))
        __usage__()
        sys.exit(1)

    except Exception as e:
        print (str(e))
        sys.exit(2)
