import os
import re

from pandawnutil.wnmisc.misc_utils import commands_get_status_output

# ROOT file name pattern
_ROOT_FILE_PATTERN = r'\.root(\.\d+)*$'

# check codes. 0 is healthy and positive values mean that the file is corrupted
CHECK_OK = 0
CHECK_OPEN_FAILED = 1
CHECK_ZOMBIE = 2
CHECK_RECOVERED = 3
CHECK_CRASHED = 4
CHECK_TRUNCATED = 5
CHECK_NO_KEY_DIR = 6

# the check macro. ROOT executes the function with the same name as the macro file
_MACRO_TEMPLATE = """#include <fstream>
#include <string>
#include "TFile.h"

void {func_name}()
{{
   const char* fileNames[] = {{{file_names} 0}};
   std::ofstream ofs("{result_name}");
   for (int i = 0; fileNames[i]; ++i) {{
      // record the file name before opening it to identify the culprit if ROOT crashes
      ofs << "BEGIN\\t" << fileNames[i] << std::endl;
      ofs.flush();
      int code = {ok};
      std::string diag = "ok";
      TFile* f = TFile::Open(fileNames[i], "READ");
      if (!f) {{
         code = {open_failed};
         diag = "TFile::Open failed";
      }} else if (f->IsZombie()) {{
         code = {zombie};
         diag = "the file is zombie";
      }} else if (f->TestBit(TFile::kRecovered)) {{
         code = {recovered};
         diag = "the file was not closed properly and was recovered by ROOT";
      }} else if (f->GetEND() > f->GetSize()) {{
         code = {truncated};
         diag = "the file is truncated";
      }} else if (f->GetSeekKeys() <= 0) {{
         code = {no_key_dir};
         diag = "the key directory is unreadable";
      }} else if (f->GetNkeys() == 0) {{
         diag = "ok although the file has no keys";
      }}
      ofs << "END\\t" << code << "\\t" << diag << "\\t" << fileNames[i] << std::endl;
      ofs.flush();
      if (f) {{
         f->Close();
         delete f;
      }}
   }}
   ofs.close();
}}
"""


# check if the file name looks like a ROOT file name
def is_root_file_name(name):
    return re.search(_ROOT_FILE_PATTERN, name) is not None


# convert a string to a C++ string literal
def _to_cpp_string(src):
    return '"' + src.replace('\\', '\\\\').replace('"', '\\"') + '"'


def check_root_files(file_names, setup_env='', macro_base='__check_root_files'):
    """Check ROOT files with root.exe.

    Returns {file_name: (code, diag)} where code is 0 if the file is healthy,
    positive if the file is corrupted, and None if the check itself was unusable.
    All files are checked in a single root.exe process. The macro and the result
    file are removed before returning so that they are not picked up as outputs.
    """
    ret_map = {}
    for file_name in file_names:
        ret_map[file_name] = (None, 'not checked')
    if not file_names:
        return ret_map
    macro_name = '{0}.C'.format(macro_base)
    result_name = '{0}.out'.format(macro_base)
    try:
        # remove leftovers
        for tmp_name in [macro_name, result_name]:
            if os.path.exists(tmp_name):
                os.remove(tmp_name)
        # generate the macro with embedded file names to avoid quoting problems
        with open(macro_name, 'w') as macro_file:
            macro_file.write(_MACRO_TEMPLATE.format(
                func_name=macro_base,
                file_names=''.join(['{0}, '.format(_to_cpp_string(n)) for n in file_names]),
                result_name=result_name,
                ok=CHECK_OK,
                open_failed=CHECK_OPEN_FAILED,
                zombie=CHECK_ZOMBIE,
                recovered=CHECK_RECOVERED,
                truncated=CHECK_TRUNCATED,
                no_key_dir=CHECK_NO_KEY_DIR))
        # run root.exe
        com = '{0}root.exe -b -q -l -n {1}'.format(setup_env, macro_name)
        print(com)
        tmp_status, tmp_out = commands_get_status_output(com)
        # print the output since ROOT's own diagnostics are useful
        print(tmp_out)
        if tmp_status != 0:
            print('WARNING: root.exe failed with {0}'.format(tmp_status))
        # parse the result
        if not os.path.exists(result_name):
            print('WARNING: cannot check ROOT files since {0} was not produced'.format(result_name))
            return ret_map
        with open(result_name) as result_file:
            for line in result_file:
                items = line.rstrip('\n').split('\t')
                if items[0] == 'BEGIN' and len(items) > 1:
                    # ROOT crashed while opening this file unless an END line follows
                    ret_map['\t'.join(items[1:])] = (CHECK_CRASHED, 'root.exe crashed while opening the file')
                elif items[0] == 'END' and len(items) > 3:
                    ret_map['\t'.join(items[3:])] = (int(items[1]), items[2])
    except Exception as e:
        print('WARNING: cannot check ROOT files due to {0}'.format(str(e)))
    finally:
        # remove the macro and the result file not to stage them out
        for tmp_name in [macro_name, result_name]:
            try:
                if os.path.exists(tmp_name):
                    os.remove(tmp_name)
            except Exception:
                pass
    return ret_map
