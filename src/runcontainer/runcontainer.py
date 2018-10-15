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

import os
import sys
import time
import argparse
import logging
import urllib
import ast
import subprocess

# Example of prun command to process
# prun --exec 'pwd && ls -l %IN %OUT' --outDS user.aforti.test$a \
#      --outputs out.dat --site=ANALY_MANC_SL7 --noBuild \
#      --inDS user.aforti.test5_out.dat.197875784

# Examples of runGen command to process. For containers
# they'll be simpler, but since we are shadowing runGen
# we have to catch also what we don't process
#
# -j "" --sourceURL https://aipanda078.cern.ch:25443 -r .
# -p "chmod%20777%20run_grid.sh%3B%20./run_grid.sh%20229%20input.in%20
#     --proc%20wm%20--mbins%2032%2C40%2C200%20--pdfset%20ATLAS-epWZ16-EIG%20
#     --pdfvar%200%20--order%202%20--kmufac%201%20--kmuren%201%20
#     --verbose%20%3B"
# -l panda.0911074511.596244.lib._15353637.14628477940.lib.tgz
# -o "{'results.txt': 'user.sawebb.15353637._000229.results.txt',
#      'results.root': 'user.sawebb.15353637._000229.results.root'}"
# --rootVer 6.04.18
#
# -j "" --sourceURL https://aipanda078.cern.ch:25443 -r ./
# -p "runjob.sh%20data17_13TeV.00339562.physics_Main.deriv.DAOD_HIGG2D1.
#     f889_m1902_p3402"
# -l panda.0914165400.532678.lib._15386194.14657955419.lib.tgz
# -o "{'hist-output.root': 'user.milu.15386194._000006.hist-output.root',
#      'myOutput.root': 'user.milu.15386194._000006.myOutput.root'}"
# -i "['DAOD_HIGG2D1.12820426._000058.pool.root.1',
#      'DAOD_HIGG2D1.12820426._000059.pool.root.1',
#      'DAOD_HIGG2D1.12820426._000060.pool.root.1',
#      'DAOD_HIGG2D1.12820426._000061.pool.root.1',
#      'DAOD_HIGG2D1.12820426._000062.pool.root.1',
#      'DAOD_HIGG2D1.12820426._000063.pool.root.1',
#      'DAOD_HIGG2D1.12820426._000064.pool.root.1',
#      'DAOD_HIGG2D1.12820426._000065.pool.root.1']"
# --useAthenaPackages
# --useCMake
# --rootVer 6.12.06
# --writeInputToTxt IN:input.txt

VERSION = "1.0.10"


def main():

    """ Main function of run_container """

    logging.info("runcontainer version: "+VERSION)
    logging.info("Start time: "+time.ctime())

    sc = singularity_command()
    run_container(sc)
    rename_ouput()

    logging.info("End time: "+time.ctime())


def singularity_command():

    # Options for the command line string have default values or are mandatory

    # Base singularity command
    singularity_base = 'singularity -s exec -C'

    # If Cvmfs add that to bind_paths
    cvmfs = ''
    if args.ctr_cvmfs:
        cvmfs = '-B /cvmfs:/cvmfs'

    logging.debug("Command to run in the container %s", args.ctr_cmd)
    if ';' in args.ctr_cmd:
        logging.error("Multiple commands not allowed with " +
                      "containers please use && to concatenate them")
        sys.exit(1)

    command = args.ctr_cmd.replace('%IN', input())

    pwd = os.environ['PWD']
    singularity_cmd = "%s --pwd %s -B %s:%s %s %s %s" % \
                      (singularity_base,
                       args.ctr_workdir,
                       pwd,
                       args.ctr_datadir,
                       cvmfs,
                       args.ctr_image,
                       command)

    logging.debug("Singularity command: %s", singularity_cmd)
    return singularity_cmd


def run_container(cmd=''):

    logging.info("Start container time: "+time.ctime())

    try:
        output = subprocess.check_output(cmd, shell=True)
    except subprocess.CalledProcessError as cpe:
        logging.error("Status : FAIL", cpe.returncode, cpe.output)
    else:
        logging.info(output)

    logging.info("End container time: "+time.ctime())


def input():

    input_string = ''

    if args.input_files:
        logging.info("Input files %s" % args.input_files)
    else:
        logging.info("No input files requested")

    for filename in args.input_files:
        if os.path.isfile(filename):
            filename = os.path.join(args.ctr_datadir, filename)
            input_string += "%s," % filename
        else:
            logging.info("Input file %s is missing", filename)

    input_string = input_string[:-1]

    # Write input files string to a text file
    if args.input_text:
        # RunGen requires a 'IN' keyword as part of the argument
        key, text_file = args.input_text.split(':')
        if key == 'IN':
            f = open(text_file, 'w')
            f.write(input_string)
            f.close()
        else:
            logging.error("Missing IN keyword in the argument IN:filename")

    return input_string


def rename_ouput():

    # Rename the output files. No need to move them to currentDir
    # because we are already there. PFC and jobreport.json at
    # a later stage all jobs I checked have them empty anyway
    for old_name, new_name in args.output_files.iteritems():
        # archive *
        if old_name.find('*') != -1:
            tar_cmd = 'tar -zcvf '+new_name+'.tgz '+old_name
            logging.debug("rename_output tar command: "+tar_cmd)
            subprocess.check_output(tar_cmd, shell=True)
        else:
            mv_cmd = 'mv '+old_name+' '+new_name
            logging.debug("rename_output mv command: "+mv_cmd)
            subprocess.check_output(mv_cmd, shell=True)


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
    arg_parser.add_argument('--containerWorkDir',
                            dest='ctr_workdir',
                            default="/work",
                            help='Change workdir inside the container. \
                                  Default: /')

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
