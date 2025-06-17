import os
import json
import sys

# Base error codes for worker node scripts
_BASE_ERROR_CODES = {
    1: ('MISSING_ARGUMENT', 'Missing argument'),
    2: ('CMT_FAILURE', 'CMT failure'),
    3: ('FAILED_TO_GET_TARBALL', 'Failed to download tarball'),
    4: ('NO_ROOT', 'No Root'),
    5: ('BAD_POLL_FILE_CATALOG', 'Bad Poll File Catalog'),
    6: ('ATHENA_FAILURE', 'Athena Failure'),
    7: ('ALL_INPUT_UNAVAILABLE', 'No input files available'),
    8: ('SOME_INPUT_UNAVAILABLE', 'Some input files unavailable'),
    9: ('CORRUPTED_TARBALL', 'Tarball is corrupted'),
    10: ('DB_RELEASE_FAILURE', 'DBRelease Failure'),
    11: ('FAILED_TO_GET_EVENT', 'Failed to get events for HPO'),
    12: ('NO_MORE_EVENTS', 'No more events available for HPO'),
    13: ('HPO_EXECUTION_FAILURE', 'HPO payload execution failure'),
    14: ('MAX_LOOP_COUNT_EXCEEDED', 'Max loop count exceeded for HPO'),
    15: ('NO_OUTPUT', 'No output files found'),
    16: ('OUTPUT_MISSING', 'Output files are missing'),
    17: ('EXEC_SCRIPT_NOT_FOUND', 'Exec Script Not Found'),
    18: ('PAYLOAD_FAILURE', 'Payload execution failure'),
    19: ('GOOD_RUN_LIST_FAILURE', 'Good Run List failure'),
    20: ('GET_GOOD_RUN_LIST', 'Failed to get Good Run List'),
    21: ('UNSUPPORTED_FILE_TYPE', 'Unsupported file type'),
}

# Offset for each worker node script
_OFFSET_DICT = {
    'buildJob': 100,
    'buildGen': 200,
    'runGen': 300,
    'runAthena': 400,
    'runHPO': 500,
    'runMerge': 600,
    'preGoodRunList': 700
}

# Global offset for all worker node script error codes
_GLOBAL_OFFSET = 5000

class OneError:
    """Class to represent a single error code with its message."""
    def __init__(self, code, message, offset):
        self.code = code
        self.message = message
        self.offset = offset
        self.base_dir = os.getcwd()

    def dump(self, message=None):
        """Produce an error report JSON and print message to stdout."""
        if message is None:
            message = self.message
        error_report = dict()
        error_report['error_code'] = self.code + self.offset
        error_report['error_diag'] = message
        print("ERROR: %s" % message)
        with open(os.path.join(self.base_dir, 'payload_error_report.json'), 'w') as f:
            json.dump(error_report, f)
        return

    def exit(self, message=None):
        """Produce an error report JSON and exit the program with the error code and message."""
        self.dump(message)
        sys.exit(self.code)

    def __str__(self):
        """String representation of the error."""
        return "ErrorCode=%s" % self.code + self.offset


class ErrorCodes:
    """Class to manage error codes for worker node scripts.
    Each script has its own set of error codes, offset by a base value.
    """
    def __init__(self, script_name):
        offset =_OFFSET_DICT[script_name] + _GLOBAL_OFFSET
        for code, (key, desc) in _BASE_ERROR_CODES.items():
            setattr(self, key, OneError(code, desc, offset))
