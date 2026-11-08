"""
Temporary backward-compatibility shim for database module.
Re-exports from wave.db for backward compatibility.
Temporary shim per R3 Step 3; to be removed in Step 9.
"""
import sys
from wave.db import Database

sys.modules[__name__].Database = Database

__all__ = ["Database"]
