"""Read-only SQLAdmin view for administrative audit events."""

from sqladmin import ModelView

from ...interfaces.admin.mixins import DataclassModelMixin
from .models import AdminAuditLog


class AdminAuditLogAdmin(DataclassModelMixin, ModelView, model=AdminAuditLog):
    """Expose the audit trail without allowing operators to rewrite it."""

    name = "Audit event"
    name_plural = "Audit log"
    icon = "fa-solid fa-shield-halved"
    category = "Security"

    column_list = [
        AdminAuditLog.id,
        AdminAuditLog.created_at,
        AdminAuditLog.actor,
        AdminAuditLog.action,
        AdminAuditLog.entity,
        AdminAuditLog.entity_id,
        AdminAuditLog.ip_address,
    ]
    column_details_list = [
        AdminAuditLog.id,
        AdminAuditLog.created_at,
        AdminAuditLog.actor,
        AdminAuditLog.action,
        AdminAuditLog.entity,
        AdminAuditLog.entity_id,
        AdminAuditLog.changes,
        AdminAuditLog.ip_address,
        AdminAuditLog.user_agent,
    ]
    column_searchable_list = [AdminAuditLog.actor, AdminAuditLog.action, AdminAuditLog.entity, AdminAuditLog.entity_id]
    column_sortable_list = [AdminAuditLog.id, AdminAuditLog.created_at, AdminAuditLog.actor, AdminAuditLog.entity]
    column_default_sort = [(AdminAuditLog.id, True)]

    can_create = False
    can_edit = False
    can_delete = False
    can_view_details = True
    can_export = False
