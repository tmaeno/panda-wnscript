#!/usr/bin/env python
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# http://www.apache.org/licenses/LICENSE-2.0
#
# Container TRF. It shadows runGen.py (T. Maeno) when the user
# runs prun with --containerImage the pilot will run this code instead
# of runGen.py. There are several runGen options that are not used here
# but are automatically added by the system. The script will just log
# them without failures.
#
# Authors:
# - Alessandra Forti, alessandra.forti@cern.ch, 2018
#######################################################################

import os
import sys
import time
import glob
import argparse
import logging
import urllib
import ast
import subprocess
import shlex

VERSION = '1.0.21'

def main():

    """ Main function of run_container """

    logging.info("runcontainer version: "+VERSION)
    logging.info("Start time: "+time.ctime())

    run_container()
    rename_ouput()

    logging.info("End time: "+time.ctime())

    
def singularity_sandbox():

    # We need to sandbox because singularity is stupid
    if 'PILOT_HOME' not in os.environ:
        os.environ['PILOT_HOME'] = os.environ['PWD']
    os.environ['SINGULARITY_TMPDIR'] = os.environ['PILOT_HOME']+'/singularity_tmp'
    target_image=os.environ['SINGULARITY_TMPDIR']+'/image'
 
    if os.path.exists(target_image):
        sing_cmd="singularity check {}".format(target_image) 
    else:
        os.mkdir(os.environ['SINGULARITY_TMPDIR'],0o755)
        os.environ['SINGULARITY_LOCALCACHEDIR'] = os.environ['SINGULARITY_TMPDIR']
        os.environ['SINGULARITY_CACHEDIR'] = os.environ['SINGULARITY_TMPDIR']+'/cache'
        sing_cmd="singularity build --sandbox {} {}".format(target_image,
                                                            args.ctr_image)
    
    logging.info("Singularity command: %s", sing_cmd)

    execute(shlex.split(sing_cmd))


def singularity_container():

    # Options for the command line string have default values or are mandatory

    # Base singularity command
    singularity_base = 'singularity exec'

    # If Cvmfs add that to bind_paths
    cvmfs = ''
    if args.ctr_cvmfs:
        cvmfs = '-B /cvmfs:/cvmfs'

    logging.debug("Command to run in the container %s", args.ctr_cmd)

    # Replace input place holders
    command = args.ctr_cmd
    files_map = input()
    for key in sorted(files_map.keys(), reverse=True, key = lambda x: len(x)):
        if key in command:
            command = command.replace('%'+key,files_map[key])
    
    # Write the command into a script.
    # Makes it easier to handle whatever character 
    # is passed to the script
    file_name = '_runcontainer.sh'
    open(file_name,'w').write(command+'\n')
    os.chmod(file_name,0o700)
    logging.info("User command: %s", command)
    pwd = os.environ['PWD']
    cmd = args.ctr_datadir+'/'+file_name

    # Compose the command
    # Need to update when I'll parse queuedata
    target_image=os.environ['SINGULARITY_TMPDIR']+'/image'
    singularity_cmd = "%s --pwd %s -B %s:%s %s %s %s" % \
                      (singularity_base,
                       args.ctr_datadir,
                       pwd,
                       args.ctr_datadir,
                       cvmfs,
                       target_image,
                       cmd)
    logging.info("Singularity command: %s", singularity_cmd)

    execute(shlex.split(singularity_cmd))


def execute(cmd=[]):

    try:

        ch = subprocess.Popen(cmd, stdout = subprocess.PIPE, bufsize = 1)
        for line in iter(ch.stdout.readline,b''):
            logging.info(line.strip())
        ch.stdout.close()
    except subprocess.CalledProcessError as cpe:
        logging.error("Status : FAIL, Container execution failed with errors "+
                      "check payload.stderr. Error code : %s\n%s",
                      cpe.returncode, cpe.output)
        sys.exit(cpe.returncode)
        

def run_container():

    logging.info("Start container time: "+time.ctime())

    # to review when more than one container
    # or when I'll parse queue data
    singularity_sandbox()
    singularity_container()

    logging.info("End container time: "+time.ctime())


def input():

    # Dictionary to merge --inDS --inMap options and treat them in the same way
    in_map = {}

    if args.input_map:
        logging.info("Input primary and secondary files %s" % args.input_map)
        in_map = args.input_map
    elif args.input_files:
        logging.info("Input files %s" % args.input_files)
        in_map['IN'] = args.input_files
    else:
        logging.info("No input files requested")
    for key, in_files in in_map.iteritems():
        input_string = ''
        for filename in in_files:
            if os.path.isfile(filename):
                filename = os.path.join(args.ctr_datadir, filename)
                input_string += "%s," % filename
                in_map[key] = input_string[:-1]
            else:
                logging.info("Input file %s is missing: ", filename)

    # Write input files string to a text file
    if args.input_text:
        # Write input files if needed
        for a in args.input_text.split(','):
            file_key, text_file = a.split(':')
            if file_key in in_map.keys():
                f = open(text_file, 'w')
                f.write(in_map[file_key])
                f.close()
            else:
                logging.error("Key %s doesn't match any of the input keys " +
                              "%s will not create corresponding file %s",
                              file_key, in_map.keys(), text_file)
    logging.debug("Input files map: %s", in_map)
    return in_map


def rename_ouput():

    current_dir = os.environ['PWD']
    # Rename the output files. No need to move them to currentDir
    # because we are already there. PFC and jobreport.json at
    # a later stage all jobs I checked have them empty anyway
    for old_name, new_name in args.output_files.iteritems():
        # archive *
        if old_name.find('*') != -1:
            for root, dirs, files in os.walk(current_dir):
                for folder in dirs:
                    out_folder = os.path.join(root, folder)
                    try:
                        os.chdir(out_folder)
                        if glob.glob(old_name):
                            tar_cmd = ('tar -zcvf '+current_dir+'/'+new_name +
                                       '.tgz '+old_name)
                            logging.debug("rename_output tar command: " +
                                          tar_cmd)
                            subprocess.check_output(tar_cmd, shell=True)
                            break
                    except OSError as err:
                        logging.error("Cannot chdir. Error: "+format(err))
                        pass
        else:
            output_path = ''
            for root, dirs, files in os.walk(current_dir):
                if old_name in files:
                    output_path = os.path.join(root, old_name)
                    mv_cmd = 'mv '+output_path+' '+new_name
                    logging.debug("rename_output mv command: "+mv_cmd)
                    try:
                        subprocess.check_output(mv_cmd, shell=True)
                    except OSError as err:
                        logging.error("Cannot mv: "+format(err))


if __name__ == "__main__":

    arg_parser = argparse.ArgumentParser()

    # Required arguments
    required = arg_parser.add_argument_group('required arguments')

    # Command to execute
    required.add_argument('-p',
                          dest='ctr_cmd',
                          type=urllib.unquote,
                          required=True,
                          help='Command to execute in the container')

    # Container Image to use
    required.add_argument('--containerImage',
                          dest='ctr_image',
                          required=True,
                          help='Image path in CVMFS or on docker')

    # Optional arguments

    # Container output dataset
    arg_parser.add_argument('-o',
                            dest='output_files',
                            type=ast.literal_eval,
                            default="{}",
                            help='Output files')

    # Container input dataset
    arg_parser.add_argument('-i',
                            dest='input_files',
                            type=ast.literal_eval,
                            default="[]",
                            help='Input files')

    # Container output dataset
    arg_parser.add_argument('--inMap',
                            dest='input_map',
                            type=ast.literal_eval,
                            default="{}",
                            help='Input files mapping')

    # Some users prefer reading the input string from file
    # might be the best also for containers
    arg_parser.add_argument('--writeInputToTxt',
                            dest='input_text',
                            default="",
                            help='Write input to a text file')

    # Container data directory
    arg_parser.add_argument('--containerDataDir',
                            dest='ctr_datadir',
                            default="/data",
                            help='Change directory where input, output \
                                  and log files should be stored. \
                                  Default: /data')
    # Container workdir
#    arg_parser.add_argument('--containerWorkDir',
#                            dest='ctr_workdir',
#                            default="/data",
#                            help='Change workdir inside the container. \
#                                  Default: /')

    # Container cvmfs
    arg_parser.add_argument('--containerCvmfs',
                            dest='ctr_cvmfs',
                            action='store_true',
                            default=False,
                            help='Mount /cvmfs. Default false')

    # Container proxy
    arg_parser.add_argument('--containerX509',
                            dest='ctr_x509',
                            action='store_true',
                            default=False,
                            help='Set the X509_USER_PROXY \
                                  and X509_CA_CERTDIR. Default: false')

    # Container environment vars
    arg_parser.add_argument('--containerEnv',
                            dest='ctr_env',
                            default="",
                            help='Container environment variables')

    # Debug
    arg_parser.add_argument('--debug',
                            dest='debug',
                            action='store_true',
                            default=False,
                            help='Enable debug mode for logging messages')

    args, unknown = arg_parser.parse_known_args()

    # Setup the logging level
    format_str = '%(asctime)s | %(levelname)-8s | %(message)s'
    if args.debug:
        logging.basicConfig(stream=sys.stdout, level=logging.DEBUG,
                            format=format_str)
    else:
        logging.basicConfig(stream=sys.stdout, level=logging.INFO,
                            format=format_str)
    logging.basicConfig(stream=sys.stderr, level=logging.ERROR,
                        format=format_str)

    if unknown:
        logging.info("Following arguments are unknown or unsupported %s" %
                     unknown)

    main()
