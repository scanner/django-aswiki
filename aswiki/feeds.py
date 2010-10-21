"""
RSS/Atom Feeds for our aswiki
"""

# Django imports
#
from django.core.urlresolvers import reverse
from django.contrib.syndication.feeds import Feed

# Model imports
#
from aswiki.models import Topic, NascentTopic

###########################################################################
#
class LatestTopicFeed(Feed):
    """
    A RSS/Atom feed of the most recently modified topics.
    """
    title = "Recent topics"
    description = "The most recently modified topics"

    title_template = 'aswiki/feeds/topic_title.html'
    description_template = 'aswiki/feeds/topic_description.html'

    ####################################################################
    #
    def link(self):
        """
        The link to what this feed represents.. in this case our
        index of topics.
        """
        return reverse('aswiki.views.topic_list')

    ####################################################################
    #
    def items(self):
        """
        The 15 most recently modified topics.
        """
        return Topic.objects.order_by('-modified')[:15]

###########################################################################
#
class LatestNascentTopicFeed(Feed):
    """
    A RSS/Atom feed of the most created nascent topics.
    """
    title = "Recent nascent topics"
    description = "The most recent nascent topics"

    title_template = 'aswiki/feeds/topic_title.html'
    description_template = 'aswiki/feeds/topic_description.html'

    ####################################################################
    #
    def link(self):
        """
        The link to what this feed represents.. in this case our
        index of nascent topics.
        """
        return reverse('aswiki_nascent_index')

    ####################################################################
    #
    def item_link(self, obj):
        """
        Given a NascentTopic provide a link to create it..

        Arguments:
        - `obj`: The NascentTopic.
        """
        return reverse('aswiki_topic', args = [obj.name])

    ####################################################################
    #
    def items(self):
        """
        The 15 most recently created nascent topics.
        """
        return NascentTopic.objects.order_by('-created')[:15]
