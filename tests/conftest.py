#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Pytest bootstrap for local package imports.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
