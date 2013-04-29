#
# File: $Id: urls.py 1898 2008-11-04 08:19:18Z scanner $
#
"""
URLConf for the Django aswiki app.

Recommended usage is a call to ``include()`` in your project's root
URLConf to include this URLConf for any URL beginning with
`/aswiki/`.
"""

# Django imports
#
from django.conf.urls.defaults import *
from django.conf import settings
# from django.contrib.syndication.views import feed

# Model imports
#
from aswiki.models import Topic, NascentTopic

#
# aswiki imports
#
from aswiki.feeds import LatestTopicFeed, LatestNascentTopicFeed
from aswiki import views

# If we have the 'asutils.middleware.RequireLogin' middleware then by
# default all of our views will require users to be logged in. This will
# fail for our rss feeds so, in that case we want to import the wrapper
# functions that we can use to require our rss feeds to use HTTP basic auth
# to authenticate a user. This is a bit backwards as we have to allow
# anonymous wrapped around the function that requires HTTP basic auth.
#
# if 'asutils.middleware.RequireLogin' in settings.MIDDLEWARE_CLASSES:
#     try:
#         from asutils.decorators import view_or_basicauth
#         from asutils.middleware import allow_anonymous

#         @allow_anonymous
#         def basic_auth_feed(request, url, feed_dict = None):
#             args = (url,)
#             kwargs = { 'feed_dict' : feed_dict }
#             return view_or_basicauth(feed, request,
#                                      lambda u: u.is_authenticated(),
#                                      *args, **kwargs)
#     except ImportError:
#         def basic_auth_feed(request, url, feed_dict = None):
#             return feed(request, url, feed_dict)



# The dictionary that describes our rss feeds..
#
feeds = { 'topics' : LatestTopicFeed,
          'nascent_topics' : LatestNascentTopicFeed }

# See if we have a front page defined in our settings. If we do not then
# default it.
#
front_page = getattr(settings,'ASWIKI_FRONTPAGE','FrontPage')

###########################################################################
#
urlpatterns = patterns(
    '',
    # The top page in our wiki is a wiki page. It calls the exact
    # same view as 'aswiki_topic' except that the topic name
    # comes from your settings module if provided. Otherwise
    # we use the default 'FrontPage' topic.
    #
    url('^$',
        'django.views.generic.simple.redirect_to',
        {'url' : 'topic/%s/' % front_page },
        name = 'aswiki_frontpage'),

    url(r'^topic/$',
        'aswiki.views.topic_list',
        { 'template_name' : 'aswiki/topic_list.html',
          'queryset'      : Topic.objects.all(),
          'paginate_by'   : 20},
        name = 'aswiki_topic_index'),

    # The URL for a topic is 'topic/<any set of characters, url
    # quoted, except '/'>/. This lets us also have urls like
    # "topic/foo/2008-08-13_12:22:24/" which is what we use for
    # accessing previous versions of a topic.
    #
    url(r'^topic/(?P<topic_name>[^/]+)/$',
        'aswiki.views.topic',
        { 'template_name' : 'aswiki/topic.html' },
        name = 'aswiki_topic'),

    # For attachments/images they are relative to the topic's url, and
    # when previewing from the edit page, the /edit/ url. The key
    # element is that they do not end in a '/'.
    #
    # We need to replicate this for .../edit/ as well so that images show
    # up when previewing edits.
    #
    url(r'^topic/(?P<topic_name>[^/]+)/(?P<attachment_name>[^/]+)$',
        'aswiki.views.topic_attachment',
        name = 'aswiki_topic_attachment'),

    url(r'^topic/(?P<topic_name>[^/]+)/edit/(?P<attachment_name>[^/]+)$',
        'aswiki.views.topic_attachment',
        name = 'aswiki_topic_attachment_edit'),

    # For uploading image and file attachments. We use two separate
    # views so that we can have images use the image field.
    #
    url(r'^topic/(?P<topic_name>[^/]+)/upload_file/$',
        'aswiki.views.topic_upload_file',
        name = 'aswiki_topic_upload_file'),

    url(r'^topic/(?P<topic_name>[^/]+)/upload_image/$',
        'aswiki.views.topic_upload_image',
        name = 'aswiki_topic_upload_image'),

    # A user may wish to browse the versions of a topic. Note, this
    # differs from the previous url by having a trailing '/' (We can do this
    # because topic names will always be url encoded including the '/'
    # character.
    #
    url(r'^topic/(?P<topic_name>[^/]+)/versions/$',
        'aswiki.views.topic_list_versions',
        { 'template_name' : 'aswiki/topic_list_versions.html',
          'paginate_by'   : 20 },
        name = 'aswiki_topic_list_versions'),

    # This is the URL you use to edit a topic. a 'GET' gets the form
    # and a 'POST' updates it. We expect the form to have at least
    # a 'content' field, and also possibly a 'reason' field. Pass in
    # the keyword arg 'form_class' if you wish to provide your own form.
    #
    url(r'^topic/(?P<topic_name>[^/]+)/edit/$',
        'aswiki.views.topic_edit',
        { 'template_name' : 'aswiki/topic_edit.html' },
        name = 'aswiki_topic_edit'),

    url(r'^topic/(?P<topic_name>[^/]+)/rename/$',
        'aswiki.views.topic_rename',
        { 'template_name' : 'aswiki/topic_rename.html' },
        name = 'aswiki_topic_rename'),

    url(r'^topic/(?P<topic_name>[^/]+)/delete/$',
        'aswiki.views.topic_delete',
        { 'template_name' : 'aswiki/topic_delete.html' },
        name = 'aswiki_topic_delete'),

    # This view controls setting two properties on topics: lock &
    # restricted. Unlike edit, rename, or delete it does not have a
    # template.  This view will redirect the user back to the
    # topic. This is a separate view from 'edit' because it requires a
    # permissions check to see if the user has the permission to
    # lock/unlock a topic, or restrict/unrestrict a topic.
    #
    # XXX We will need to visit how this sort of view works in the
    #     future with respect to things like JSON.
    #
    url(r'^topic/(?P<topic_name>[^/]+)/set_property/$',
        'aswiki.views.topic_set_property',
        name = 'aswiki_topic_set_property'),

    # And as indicated above, a URL for getting a previous version
    # of a topic.
    #
    # NOTE: This view is actually a bit more flexible in that if it is
    #       given a date that does not correspond to a previous version
    #       of a topic, if there is a version earlier then the given date
    #       it will do a http redirect to the url for that version.
    #
    url(r'^topic/(?P<topic_name>[^/]+)/versions/(?P<created>\d\d\d\d-\d\d-\d\d_\d\d:\d\d:\d\d)/$',
        'aswiki.views.topic_version',
        { 'template_name' : 'aswiki/topic_version.html' },
        name = 'aswiki_topic_version'),

    url(r'^topic/(?P<topic_name>[^/]+)/versions/(?P<created>\d\d\d\d-\d\d-\d\d_\d\d:\d\d:\d\d)/revert/$',
        'aswiki.views.topic_revert',
        { 'template_name' : 'aswiki/topic_revert.html' },
        name = 'aswiki_topic_revert'),

    # And our simple feeds.. topic index and nascent topic index.
    #
    # url(r'^feeds/(?P<url>.*)/$',
    #     basic_auth_feed,
    #     {'feed_dict': feeds},
    #     name = 'aswiki_feeds'),

    # Nascent topics are ones that do not exist yet but another topic refers
    # to them by name.. we provide views that let you browse these nascent
    # topics so you can see what still needs to be created.
    #
    url(r'^nascent/$',
        views.NascentTopicList.as_view(
            template_name='aswiki/nascent_topic_list.html'),
        name='aswiki_nascent_index'),
    )
