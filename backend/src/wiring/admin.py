"""The model views the admin panel registers.

Written by the generator in `tools/removal_drill.py`, which a test compares this file against.
"""

from ..modules.audit_log.admin import AdminAuditLogAdmin
from ..modules.role.admin import RoleAdmin, RolePermissionAdmin, UserRoleAdmin
from ..modules.social.admin import LessonCommentAdmin, LessonCommentReportAdmin
from ..modules.tier.admin import TierAdmin
from ..modules.user.admin import UserAdmin

ADMIN_VIEWS: tuple[type, ...] = (
    UserAdmin,
    LessonCommentAdmin,
    LessonCommentReportAdmin,
    TierAdmin,
    RoleAdmin,
    RolePermissionAdmin,
    UserRoleAdmin,
    AdminAuditLogAdmin,
)
