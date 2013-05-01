"""
The management command suite for the aswiki app.

Very little happens here. Main purpose is to register some
notification types if you have the notification app installed.
"""
from django.db.models.signals import post_syncdb
from django.conf import settings

# If we are able to import the 'notification' module then attach a
# hook to the 'post_syncdb' signal that will create a new notice type
# for aswiki. This lets us hook in to the notification framework to
# keep track of topic changes.
#
if "notification" in settings.INSTALLED_APPS:
    from notification.models import NoticeType

    ########################################################################
    #
    def create_notice_types(sender, **kwargs):
        NoticeType.create("aswiki_topic_change",
                          "Topic Change",
                          "A Topic you are following has changed.")
        return

    ########################################################################
    #
    post_syncdb.connect(create_notice_types)

else:
    print "Skipping creation of NoticeTypes as notification app not found"

