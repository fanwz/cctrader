#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2018/10/22 15:43
# @Author  : AMR
# @File    : header.py
# @Software: PyCharm

import platform
import time
import os
import sys
import re
import json
import io

is_win_f = False
if platform.system() == "Windows":
    is_win_f = True

def py2_jsondump(data, filename):
    with io.open(filename, 'w', encoding = 'utf-8') as f:
        f.write(json.dumps(data, f, ensure_ascii = False, sort_keys = True, indent = 2))

def py3_jsondump(data, filename):
    with io.open(filename, 'w', encoding = 'utf-8') as f:
        return json.dump(data, f, ensure_ascii = False, sort_keys = True, indent = 2)

def jsonload(filename):
    with io.open(filename, 'r', encoding = 'utf-8') as f:
        return json.load(f)

if sys.version_info[0] == 2:
    jsondump = py2_jsondump
elif sys.version_info[0] == 3:
    jsondump = py3_jsondump

def is_number(s,isfloat=False):
    if isfloat:
        try:
            float(s)
            return True
        except ValueError:
            pass
    else:
        try:
            int(s)
            return True
        except ValueError:
            pass

        try:
            import unicodedata
            unicodedata.numeric(s)
            return True
        except (TypeError,ValueError):
            pass

    return False