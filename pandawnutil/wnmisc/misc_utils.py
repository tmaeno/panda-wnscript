import os
import json
import time
try:
    from urllib.request import urlopen
    from urllib.error import HTTPError
except ImportError:
    from urllib2 import urlopen, HTTPError
import ssl
import subprocess

# internal env variable to record the execution home directory name
ENV_HOME = 'TRF_EXEC_HOME_DIR'

# env variable of payload input directory
ENV_WORK_DIR = 'PAYLOAD_INPUT_DIR'


# add user job metadata
def add_user_job_metadata():
    # check user metadata
    userJobMetadata = 'userJobMetadata.json'
    if not os.path.exists(userJobMetadata):
        return
    # size check
    if os.stat(userJobMetadata).st_size > 1024*1024:
        print ("WARNING : user job metadata is too large > 1MB")
        return
    merged_dict = dict()
    # get user metadata
    try:
        with open(userJobMetadata) as f:
            tmp_dict = json.load(f)
    except Exception:
        print ("ERROR : user job metadata is corrupted")
        return
    # check job report
    jobReport = 'jobReport.json'
    if os.path.exists(jobReport):
        with open(jobReport) as f:
            merged_dict = json.load(f)
        os.rename(jobReport, jobReport+'.org')
    # add
    merged_dict['user_job_metadata'] = tmp_dict
    # version number
    if 'reportVersion' not in merged_dict:
        merged_dict['reportVersion'] = '1.0.0'
    # dump
    with open(jobReport, 'w') as f:
        json.dump(merged_dict, f)


# get file via http
def get_file_via_http(base_url='', file_name='', full_url=''):
    if full_url == '':
        url = "%s/cache/%s" % (base_url, file_name)
    else:
        url = full_url
        if file_name == '':
            file_name = url.split('/')[-1]
    print ("--- Getting file from %s" % url)
    # the file already exists in the current directory
    if os.path.exists(file_name):
        print ("skip since the file already exists in the current directory")
        return True, None
    # the file exists in the home directory or payload working directory
    for tmpEnv in [ENV_HOME, ENV_WORK_DIR]:
        if tmpEnv in os.environ:
            fileInHome = os.path.join(os.environ[tmpEnv], file_name)
            if os.path.exists(fileInHome):
                # make symlink
                os.symlink(fileInHome, file_name)
                print ("skip since the file is available in {0}".format(os.environ[tmpEnv]))
                return True, None
    isOK = False
    errStr = None
    for i in range(3):
        try:
            try:
                context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
            except Exception:
                # for old python
                res = urlopen(url)
            else:
                res = urlopen(url, context=context)
            with open(file_name, 'wb') as f:
                f.write(res.read())
            isOK = True
            break
        except HTTPError as e:
            errStr = 'HTTP code: {0} - Reason: {1}'.format(e.code, e.reason)
            # doesn't exist
            if e.code == 404:
                break
        except Exception as e:
            errStr = str(e)
            time.sleep(30)
    if not isOK:
        return False, "Cannot download the user sandbox with {0}".format(errStr)
    if not os.path.exists(file_name):
        return False, 'Unable to fetch %s from web' % file_name
    print ("succeeded")
    return True, None


# replacement for commands
def commands_get_status_output(com):
    data = ''
    try:
        # not to use check_output for python 2.6
        # data = subprocess.check_output(com, shell=True, universal_newlines=True, stderr=subprocess.STDOUT)
        p = subprocess.Popen(com, shell=True, universal_newlines=True, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT)
        data, unused_err = p.communicate()
        retcode = p.poll()
        if retcode:
            ex = subprocess.CalledProcessError(retcode, com)
            raise ex
        status = 0
    except subprocess.CalledProcessError as ex:
        # commented out for python 2.6
        # data = ex.output
        status = ex.returncode
    if data[-1:] == '\n':
        data = data[:-1]
    return status, data


# record current exec directory
def record_exec_directory():
    currentDir = os.getcwd()
    os.environ[ENV_HOME] = currentDir
    print ("--- Running in %s ---" % currentDir)
    return currentDir
