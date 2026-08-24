# -*- coding: utf-8 -*-
# ASCII-named launcher so .bat can call it; runs 진우퀀트_의사결정보드.py
import os
p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "진우퀀트_의사결정보드.py")
exec(open(p, encoding="utf-8").read())
