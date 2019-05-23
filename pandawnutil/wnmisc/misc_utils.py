import os
import json

# add user job metadata
def add_user_job_metadata():
    # check user metadata
    userJobMetadata = 'userJobMetadata.json'
    if not os.path.exists(userJobMetadata):
        return
    # size check
    if os.stat(userJobMetadata).st_size > 1024*1024:
        print "WARNING : user job metadata is too large > 1MB"
        return
    merged_dict = dict()
    # get user metadata
    try:
        with open(userJobMetadata) as f:
            tmp_dict = json.load(f)
    except Exception:
        print "ERROR : user job metadata is corrupted"
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
