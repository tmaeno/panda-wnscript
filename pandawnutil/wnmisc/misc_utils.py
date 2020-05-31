import os
import json
import time
try:
    from urllib.request import urlopen, Request
    from urllib.error import HTTPError
    from urllib.parse import urlencode
except ImportError:
    from urllib import urlencode
    from urllib2 import urlopen, HTTPError, Request
import ssl
import subprocess

# internal env variable to record the execution home directory name
ENV_HOME = 'TRF_EXEC_HOME_DIR'

# env variable of payload input directory
ENV_WORK_DIR = 'PAYLOAD_INPUT_DIR'


# add user job metadata
def add_user_job_metadata(userJobMetadata='userJobMetadata.json'):
    # check user metadata
    if not os.path.exists(userJobMetadata):
        return
    # size check
    if os.stat(userJobMetadata).st_size > 1024*1024:
        print ("WARNING : user job metadata is too large > 1MB")
        return
    merged_dict = dict()
    # get user metadata
    print ("\n=== user metadata in {0} ===".format(userJobMetadata))
    try:
        with open(userJobMetadata) as f:
            print(f.read())
            f.seek(0)
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
def get_file_via_http(base_url='', file_name='', full_url='', data=None, headers=None,
                      certfile=None, keyfile=None, method=None):
    if full_url == '':
        url = "%s/cache/%s" % (base_url, file_name)
    else:
        url = full_url
        if file_name == '':
            file_name = url.split('/')[-1]
    tmpMsg = "--- Access to %s" % url
    if data is not None:
        tmpMsg += ' {0}'.format(str(data))
    print (tmpMsg)
    if data is not None:
        data = urlencode(data).encode()
    if headers is None:
        headers = {}
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
            if method is None:
                req = Request(url, data=data, headers=headers)
            else:
                try:
                    req = Request(url, data=data, headers=headers, method=method)
                except Exception:
                    # for python 2
                    class MyRequest(Request):
                        def get_method(self, *args, **kwargs):
                            return method
                    req = MyRequest(url, data=data, headers=headers)
            try:
                context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
                if certfile is not None:
                    context.load_cert_chain(certfile, keyfile)
            except Exception:
                # for old python
                res = urlopen(req)
            else:
                res = urlopen(req, context=context)
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
        return False, "Failed with {0}".format(errStr)
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


# get HPO sample
def get_hpo_sample(idds_url, task_id, sample_id):
    url = os.path.join(idds_url, 'idds', 'hpo', str(task_id), 'null', str(sample_id), 'null', 'null')
    file_name = '__tmp_get.out'
    s, o = get_file_via_http(file_name=file_name, full_url=url)
    if not s:
        return False, o
    try:
        with open(file_name) as f:
            print ('')
            print(f.read())
            f.seek(0)
            tmp_dict = json.load(f)
            for i in tmp_dict:
                if i['id'] == sample_id:
                    return True, tmp_dict
    except Exception as e:
        errStr = "failed to get the sample (ID={0}) : {1}".format(sample_id, str(e))
        return False, errStr
    return False, "cannot get the sample (ID={0}) since it is unavailable".format(sample_id)


# update HPO sample
def update_hpo_sample(idds_url, task_id, sample_id, loss):
    url = os.path.join(idds_url, 'idds', 'hpo', str(task_id), 'null', str(sample_id), str(loss))
    file_name = '__tmp_update.out'
    s, o = get_file_via_http(file_name=file_name, full_url=url, method='PUT')
    if not s:
        return False, o
    try:
        with open(file_name) as f:
            print ('')
            print(f.read())
            f.seek(0)
            tmp_dict = json.load(f)
            if tmp_dict['status'] == 0:
                return True, None
    except Exception as e:
        errStr = "failed to update the sample (ID={0}) : {1}".format(sample_id, str(e))
        return False, errStr
    return False, "cannot update the sample (ID={0}) since status is missing".format(sample_id)


# update events
def update_events(panda_url, event_id, status, certfile, keyfile):
    updateEventFileName = '__update_event.json'
    commands_get_status_output('rm -rf %s' % updateEventFileName)
    # update event
    data = dict()
    data['eventRangeID'] = event_id
    data['eventStatus'] = status
    data = {'eventRanges': json.dumps([data]), 'version': 1}
    url = panda_url + '/server/panda/updateEventRanges'
    tmpStat, tmpOut = get_file_via_http(file_name=updateEventFileName, full_url=url, data=data,
                                        headers={'Accept': 'application/json'},
                                        certfile=certfile, keyfile=keyfile)
    print ('\nstatus={0} out={1}'.format(tmpStat, tmpOut))
    if tmpStat:
        with open(updateEventFileName) as f:
            print (f.read())

