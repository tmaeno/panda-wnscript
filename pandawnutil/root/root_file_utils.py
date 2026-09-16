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

# tree name for the number of events in POOL files
_EVENT_TREE_NAME = 'CollectionTree'

# tree names which don't correspond to the number of events
_META_TREE_PATTERNS = [r'^##', r'^MetaData', r'^POOLContainer']

# max depth to look for trees in sub directories
_MAX_TREE_DEPTH = 3

# the check macro. ROOT executes the function with the same name as the macro file.
# FILE* and TString are used instead of std::ofstream and std::string since they are
# better supported by the ROOT interpreter
_MACRO_TEMPLATE = """#include <stdio.h>
#include "TClass.h"
#include "TDirectory.h"
#include "TFile.h"
#include "TKey.h"
#include "TList.h"
#include "TString.h"
#include "TTree.h"

// report the number of entries of all trees in the directory
void {func_name}_scan(TDirectory* dir, const char* fileName, TString prefix, int depth, FILE* fp)
{{
   if (depth > {max_depth}) return;
   TList* keyList = dir->GetListOfKeys();
   if (!keyList) return;
   for (int i = 0; i < keyList->GetSize(); ++i) {{
      TKey* key = dynamic_cast<TKey*>(keyList->At(i));
      if (!key) continue;
      // take only the latest cycle of each name
      if (dir->GetKey(key->GetName()) != key) continue;
      TClass* cls = TClass::GetClass(key->GetClassName());
      if (!cls) continue;
      if (cls->InheritsFrom(TTree::Class())) {{
         TTree* tree = (TTree*)key->ReadObjectAny(TTree::Class());
         if (tree) {{
            fprintf(fp, "TREE\\t%s\\t%s%s\\t%lld\\n", fileName, prefix.Data(), key->GetName(),
                    (Long64_t)tree->GetEntries());
            fflush(fp);
         }}
      }} else if (cls->InheritsFrom(TDirectory::Class())) {{
         TDirectory* subDir = dir->GetDirectory(key->GetName());
         if (subDir) {{
            {func_name}_scan(subDir, fileName, prefix + key->GetName() + "/", depth + 1, fp);
         }}
      }}
   }}
}}

void {func_name}()
{{
   const char* fileNames[] = {{{file_names} 0}};
   FILE* fp = fopen("{result_name}", "w");
   if (!fp) return;
   for (int i = 0; fileNames[i]; ++i) {{
      // record the file name before opening it to identify the culprit if ROOT crashes
      fprintf(fp, "BEGIN\\t%s\\n", fileNames[i]);
      fflush(fp);
      int code = {ok};
      const char* diag = "ok";
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
      // the verdict is reported before looking for trees so that the verdict is not lost
      // even if reading a tree crashes ROOT
      fprintf(fp, "END\\t%d\\t%s\\t%s\\n", code, diag, fileNames[i]);
      fflush(fp);
      // best-effort scan to get the number of events
      if (code == {ok} && f) {{
         {func_name}_scan(f, fileNames[i], "", 0, fp);
      }}
      if (f) {{
         f->Close();
         delete f;
      }}
   }}
   fclose(fp);
}}
"""


# check if the file name looks like a ROOT file name
def is_root_file_name(name):
    return re.search(_ROOT_FILE_PATTERN, name) is not None


# convert a string to a C++ string literal
def _to_cpp_string(src):
    return '"' + src.replace('\\', '\\\\').replace('"', '\\"') + '"'


def select_event_tree(trees):
    """Select the tree for the number of events from [(tree_path, n_entries), ...].

    CollectionTree is used for POOL files if available. Otherwise metadata trees are
    ignored and the largest tree is used when multiple trees are available.
    Returns (tree_path, n_entries) or (None, None) if nothing is usable.
    """
    # prefer CollectionTree
    for tree_path, n_entries in trees:
        if tree_path.split('/')[-1] == _EVENT_TREE_NAME:
            return tree_path, n_entries
    # ignore metadata trees
    candidates = []
    for tree_path, n_entries in trees:
        base_name = tree_path.split('/')[-1]
        is_meta = False
        for tmp_pattern in _META_TREE_PATTERNS:
            if re.search(tmp_pattern, base_name):
                is_meta = True
                break
        if not is_meta:
            candidates.append((tree_path, n_entries))
    if not candidates:
        return None, None
    # use the largest one when multiple trees are available
    candidates.sort(key=lambda tmp_item: tmp_item[1], reverse=True)
    return candidates[0]


def check_root_files(file_names, setup_env='', macro_base='__check_root_files'):
    """Check ROOT files with root.exe and get the number of events on a best-effort basis.

    Returns {file_name: {'code': .., 'diag': .., 'trees': .., 'tree': .., 'nentries': ..}}
    where code is 0 if the file is healthy, positive if the file is corrupted, and None
    if the check itself was unusable. All files are checked in a single root.exe process.
    The macro and the result file are removed before returning so that they are not
    picked up as outputs.
    """
    ret_map = {}
    for file_name in file_names:
        ret_map[file_name] = {'code': None, 'diag': 'not checked', 'trees': [],
                              'tree': None, 'nentries': None}
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
                max_depth=_MAX_TREE_DEPTH,
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
                    tmp_name = '\t'.join(items[1:])
                    if tmp_name in ret_map:
                        ret_map[tmp_name]['code'] = CHECK_CRASHED
                        ret_map[tmp_name]['diag'] = 'root.exe crashed while opening the file'
                elif items[0] == 'END' and len(items) > 3:
                    tmp_name = '\t'.join(items[3:])
                    if tmp_name in ret_map:
                        ret_map[tmp_name]['code'] = int(items[1])
                        ret_map[tmp_name]['diag'] = items[2]
                elif items[0] == 'TREE' and len(items) == 4:
                    tmp_name = items[1]
                    if tmp_name in ret_map:
                        ret_map[tmp_name]['trees'].append((items[2], int(items[3])))
        # select the tree for the number of events
        for file_name in ret_map:
            if ret_map[file_name]['trees']:
                tmp_tree, tmp_entries = select_event_tree(ret_map[file_name]['trees'])
                ret_map[file_name]['tree'] = tmp_tree
                ret_map[file_name]['nentries'] = tmp_entries
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
