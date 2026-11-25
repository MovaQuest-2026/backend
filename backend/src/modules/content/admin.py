"""SQLAdmin views for lessons and stored media."""

from sqladmin import ModelView

from ...interfaces.admin.mixins import AdminAuditMixin, DataclassModelMixin, TextCsvExportMixin
from .models import Lesson, MediaVideo


class LessonAdmin(AdminAuditMixin, DataclassModelMixin, TextCsvExportMixin, ModelView, model=Lesson):
    """Create, curate and publish the multilingual lesson catalog."""

    name = "Lesson"
    name_plural = "Lessons"
    icon = "fa-solid fa-book-open"
    category = "Content"

    column_list = [
        Lesson.slug,
        Lesson.level,
        Lesson.duration_seconds,
        Lesson.pinned,
        Lesson.coming_soon,
        Lesson.video_name,
        Lesson.updated_at,
    ]
    column_details_list = [
        Lesson.slug,
        Lesson.title_es,
        Lesson.title_en,
        Lesson.title_uk,
        Lesson.description_es,
        Lesson.description_en,
        Lesson.description_uk,
        Lesson.level,
        Lesson.duration_seconds,
        Lesson.cover_path,
        Lesson.added_at,
        Lesson.pinned,
        Lesson.coming_soon,
        Lesson.video_name,
        Lesson.created_at,
        Lesson.updated_at,
    ]
    column_searchable_list = [Lesson.slug, Lesson.title_es, Lesson.title_en, Lesson.title_uk, Lesson.video_name]
    column_sortable_list = [Lesson.slug, Lesson.level, Lesson.added_at, Lesson.pinned, Lesson.updated_at]
    column_default_sort = [(Lesson.pinned, True), (Lesson.slug, False)]

    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True
    can_export = True

    form_columns = [
        Lesson.slug,
        Lesson.title_es,
        Lesson.title_en,
        Lesson.title_uk,
        Lesson.description_es,
        Lesson.description_en,
        Lesson.description_uk,
        Lesson.level,
        Lesson.duration_seconds,
        Lesson.cover_path,
        Lesson.added_at,
        Lesson.pinned,
        Lesson.coming_soon,
        Lesson.video_name,
    ]


class MediaVideoAdmin(AdminAuditMixin, DataclassModelMixin, TextCsvExportMixin, ModelView, model=MediaVideo):
    """Inspect or remove stored videos; uploads remain bounded by the Content API."""

    name = "Video"
    name_plural = "Videos"
    icon = "fa-solid fa-film"
    category = "Content"

    column_list = [
        MediaVideo.id,
        MediaVideo.name,
        MediaVideo.content_type,
        MediaVideo.size_bytes,
        MediaVideo.checksum_sha256,
        MediaVideo.created_at,
    ]
    column_details_exclude_list = [MediaVideo.content]
    column_searchable_list = [MediaVideo.name, MediaVideo.content_type, MediaVideo.checksum_sha256]
    column_sortable_list = [MediaVideo.id, MediaVideo.name, MediaVideo.size_bytes, MediaVideo.created_at]
    column_default_sort = [(MediaVideo.id, True)]

    can_create = False
    can_edit = False
    can_delete = True
    can_view_details = True
    can_export = True
