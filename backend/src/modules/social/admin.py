"""Admin views for user comments and their reports."""

from sqladmin import ModelView

from ...interfaces.admin.mixins import AdminAuditMixin, DataclassModelMixin
from .models import LessonComment, LessonCommentReport


class LessonCommentAdmin(AdminAuditMixin, DataclassModelMixin, ModelView, model=LessonComment):
    """Review, hide, or remove reported comments."""

    name = "Comment"
    name_plural = "Comments"
    category = "Community"
    column_list = [
        LessonComment.id,
        LessonComment.lesson_id,
        LessonComment.user_id,
        LessonComment.text,
        LessonComment.is_hidden,
    ]
    column_searchable_list = [LessonComment.text, LessonComment.lesson_id]
    can_create = False
    can_edit = True
    can_delete = True
    can_export = False


class LessonCommentReportAdmin(AdminAuditMixin, DataclassModelMixin, ModelView, model=LessonCommentReport):
    """Inspect user reports without exposing a CSV export of report details."""

    name = "Comment report"
    name_plural = "Comment reports"
    category = "Community"
    column_list = [
        LessonCommentReport.id,
        LessonCommentReport.comment_id,
        LessonCommentReport.user_id,
        LessonCommentReport.reason,
        LessonCommentReport.details,
        LessonCommentReport.created_at,
    ]
    can_create = False
    can_edit = False
    can_delete = False
    can_export = False
