#
# File: $Id: admin.py 1832 2008-10-19 06:38:46Z scanner $
#
"""
Declarations of our models so that they appear in the Django admin site.
"""

from django.contrib import admin

from aswiki.models import Topic, TopicVersion, NascentTopic
from aswiki.models import ImageAttachment, FileAttachment, WriteLock

###########################################################################
#
class TopicAdmin(admin.ModelAdmin):
    list_display = ('name', 'modified', 'author')
    list_filter = ('restricted', 'modified', 'locked')
    search_fields = ('name', 'author__username', 'content_raw', 'reason')

###########################################################################
#
class WriteLockAdmin(admin.ModelAdmin):
    list_display = ('owner', 'expiry')
    list_filter = ('expiry',)
    search_fields = ('owner__username', 'topic__name')

###########################################################################
#
class TopicVersionAdmin(admin.ModelAdmin):
    list_display = ('topic', 'created', 'author')
    list_filter = ('created',)
    search_fields = ('topic__name', 'author__username', 'content_raw', 'reason')

###########################################################################
#
class NascentTopicAdmin(admin.ModelAdmin):
    list_display = ('name', 'created', 'author')
    search_fields = ('name', 'author__username')

###########################################################################
#
class FileAttachmentAdmin(admin.ModelAdmin):
    list_display = ('attachment', 'created', 'owner', 'topic')
    list_filter = ('created',)
    search_fields = ('attachment', 'owner__username', 'topic__name')

###########################################################################
#
class ImageAttachmentAdmin(admin.ModelAdmin):
    list_display = ('image', 'created', 'owner', 'topic')
    list_filter = ('created',)
    search_fields = ('image', 'owner__username', 'topic__name')

admin.site.register(Topic, TopicAdmin)
admin.site.register(WriteLock, WriteLockAdmin)
admin.site.register(TopicVersion, TopicVersionAdmin)
admin.site.register(NascentTopic, NascentTopicAdmin)
admin.site.register(FileAttachment, FileAttachmentAdmin)
admin.site.register(ImageAttachment, ImageAttachmentAdmin)

