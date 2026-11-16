"""The annotated dependencies every project has, whatever features it selected.

The ones that resolve a caller live with accounts, in ``auth/deps.py``.
"""

from typing import Annotated

from fastapi import Depends
from .database.session import DatabaseSession, async_session

AsyncSessionDep = Annotated[DatabaseSession, Depends(async_session)]
