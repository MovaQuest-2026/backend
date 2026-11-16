"""The annotated dependencies every project has, whatever features it selected.

The ones that resolve a caller live with accounts, in ``auth/deps.py``.
"""

from typing import Annotated, Any

from fastapi import Depends

from .database.session import async_session

AsyncSessionDep = Annotated[Any, Depends(async_session)]
