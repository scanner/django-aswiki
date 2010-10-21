#
# File: $Id: aswikitags.py 1858 2008-10-26 00:46:40Z scanner $
#
"""
Provides the `creole` template filter. This is not really used so much
by the aswiki app as it is by other apps that may want to render
content using creole AND have it know about the aswiki's wiki
topics. This lets any part of your project have creole markup
including working wiki links.

NOTE: The basis for this module was lifted pretty liberally from
      http://code.google.com/p/django-wikiapp/
"""

# Python standard lib imports
#
from urllib import quote

# Django imports
#
from django import template
from django.conf import settings
from django.core.urlresolvers import reverse
from django.core.exceptions import ObjectDoesNotExist

# 3rd party imports
#
import creoleparser
import aswiki.parser

# Model imports
#
from aswiki.models import Topic
from django.contrib.auth.models import User, SiteProfileNotAvailable

# what field in the profile is used to indicate a specific user's wiki
# topic?
#
ASWIKI_USER_TOPIC = getattr(settings, "ASWIKI_USER_TOPIC", "wiki_topic")

###
### This is a template library
###
register = template.Library()

####################################################################
#
@register.inclusion_tag('aswiki/topic_hierarchy.html')
def topic_hierarchy(topic):
    """
    This inclusion filter will generate HTML for use in our hierarchy
    section such that the topic named `foo.bar.biz.bat` will generate
    html that looks like: `foo >> bar >> biz >> bat` where each `foo`
    will be a link to topic `foo`, `bar` will be a link to topic
    `foo.bar`, `biz` will be a link to `foo.bar.biz` and finally `bat`
    will be a link to `foo.bar.biz.bat`

    Arguments:
    - `topic`: The Topic to generate our hierarchy links for.
    """
    # If we get a string as our argument, then we need to split it
    # directly - ie: we were not given a topic object (probably
    # because it does not exist yet.)
    #
    if isinstance(topic, basestring):
        topic_names = topic.split('.')
    else:
        topic_names = topic.name.split('.')
    building = []
    tn = []
    for topic_name in topic_names:
        building.append(topic_name)
        tn.append((topic_name, '.'.join(building)))
    return { 'topic_names'       : tn,
             'topic'             : topic }

###########################################################################
#
@register.filter
def creole(text, **kwargs):
    """
    Renders the text rendered by our version of the creole markup parser.

    Arguments:
    - `text`: The markup text to be rendered
    - `**kwargs`: Required but not used by this function.
    """
    p = creoleparser.core.Parser(dialect = aswiki.parser.dialect)

    # We need to lock the TOPIC_LIST before we render using this dialect
    # even though in this instance we do nothing with the topic list
    # that this text refers to.
    #
    try:
        aswiki.parser.TOPIC_LIST.clear_and_lock()
        text = aswiki.parser.typogrify(p.render(text))
    finally:
        aswiki.parser.TOPIC_LIST.unlock()
    return text
creole.is_safe = True

###########################################################################
#
# {% creole %} ... {% endcreole %}
#
class CreoleTextNode(template.Node):
    def __init__(self, nodelist):
        self.nodelist = nodelist

    def render(self, context):
        return creole(self.nodelist.render(context))

@register.tag("creole")
def crl_tag(parser, token):
    """
    Render the Creole into html. Will pre-render template code first.
    """
    nodelist = parser.parse(('endcreole',))
    parser.delete_first_token()
    return CreoleTextNode(nodelist)

##################################################################
##################################################################
#
class TopicInfoNode(template.Node):
    """
    Renders some information about a Topic (subject to the user's permissions)
    """
    def __init__(self, topic):
        self.topic_var = template.Variable(topic)

    def render(self, context):
        """
        Basically we render a HTML snippet with the given topic. The
        reason this is actually a templatetag is that the user may NOT
        have read permission on a topic and what template we use to
        render depends on whether they have that permission or not.
        """
        try:
            topic = self.topic_var.resolve(context)
            tmpl = "aswiki/topic_info_frag.html"

            if 'user' in context:
                user = context['user']

                if not topic.permitted(user):
                    tmpl = "aswiki/topic_info_restricted_frag.html"

            t = template.loader.get_template(tmpl)
            return t.render(template.Context({ 'topic': topic, 'user': user },
                                             autoescape = context.autoescape))

        except template.VariableDoesNotExist:
            return ''

####################################################################
#
@register.tag("topic_info")
def do_topic_info(parser, token):
    """
    Handles parsing a 'topic_info' template tag. We expect one
    argument - a variable containing the topic.

    Arguments:
    - `parser`: The django template parser object
    - `token`: The raw contents of our topic_info tag.
    """
    try:
        tag_name, topic = token.split_contents()
    except ValueError:
        raise "%r tag requires one argument" % token.contents.split()
    return TopicInfoNode(topic)

##################################################################
##################################################################
#
class EmbedASWikiTopicNode(template.Node):
    """
    Given a topic name, if the user has permission to see that topic,
    returns the rendered content of the topic.

    If no topic exists by that name, it returns a link to that topic
    so that it can be created.
    """

    ##################################################################
    #
    def __init__(self, topic):
        """
        We expect the topic name.. if it is in single or double quotes
        we treat it as the exact name of the topic. Otherwise we treat
        it as a template variable to lookup.
        """
        self.topic = topic
        return

    ##################################################################
    #
    def render(self, context):
        """
        Return an embedded wiki topic. We will return one of three
        things. '' if the user does not have permission to see this
        topic. A link to the topic if it does not exist, or the
        formatted contents of the topic, with a link to the
        topic.

        Arguments:
        - `context`: The django context object.
        """
        try:
            if self.topic[0] == self.topic[-1] and self.topic[0] in ('"', "'"):
                # If the topic is surrounded as quotes treat it as the name
                # of the topic.
                #
                topic_name = self.topic[1:-1]
            else:
                # Otherwise, treat it as a variable name that has the name
                # of the topic in it.
                #
                topic_name = template.Variable(self.topic).resolve(context)
            try:
                topic = Topic.objects.get(lc_name = topic_name.lower())
            except Topic.DoesNotExist:
                # If the topic does not exist, then return a link to the
                # topic.
                #
                if topic_name is None or len(topic_name.strip()) == 0:
                    return ""
                return u'<a href="%s">%s</a>' % (reverse('aswiki_topic',
                                                         args=(topic_name,)),
                                                 topic_name)

            # See if the user has pemission to view this topic. If they
            # do not return an empty string.
            #
            user = None
            if 'user' in context:
                user = context['user']
                if not topic.permitted(user):
                    return ''
            elif topic.restricted:
                return ''

            # Otherwise they are permitted and the topic exists. Return
            # a link to the topic and the topic's rendered content.
            #
            t = template.loader.get_template('aswiki/embedded_topic_frag.html')
            return t.render(template.Context({ 'topic': topic, 'user': user },
                                             autoescape = context.autoescape))
        except template.VariableDoesNotExist:
            return ''

####################################################################
#
@register.tag("embed_aswiki_topic")
def do_embed_aswiki_topic(parser, token):
    """
    Handles the 'embed_aswiki_topic' template tag. We expect one
    argument -- the name of the topic to embed. It can be a 'string'
    or a variable. If it is surrounded by single or double quotes it
    will be treated as a string, otherwise it will be treated as a
    template variable.

    Arguments:
    - `parser`: The django template parser object
    - `token`: The raw contents of our topic_info tag.
    """
    try:
        tag_name, topic = token.split_contents()
    except ValueError:
        raise "%r tag requires one argument" % token.contents.split()
    return EmbedASWikiTopicNode(topic)
    

####################################################################
#
@register.simple_tag
def user_wikipage(user):
    """
    A simple template tag that will render a link to the user's wiki
    page if the user has a profile and the profile has an attribute
    that is the value of 'settings.ASWIKI_USER_TOPIC'

    NOTE: ASWIKI_USER_TOPIC defaults to 'wiki_topic'

    The purpose is that whereever we would display a username, if the
    user has a wiki topic associated with them by their profile, we
    display the link to their wiki topic. This way anywhere on your
    site that you refer to users, you can also refer to that user's
    wiki topic if they have one.

    If the user has no wiki topic associated with them via their
    profile we return ''

    Arguments:
    - `user`: The user object. If this is not a django.contrib.auth.models.User
              object we return ''.
    """
    if not isinstance(user, User):
        return ""

    try:
        profile = user.get_profile()
    except (SiteProfileNotAvailable, ObjectDoesNotExist):
        return ""

    if profile is None:
        return ""
    if not hasattr(profile, ASWIKI_USER_TOPIC):
        return ""

    try:
        topic_name = getattr(profile, ASWIKI_USER_TOPIC, None)
        if topic_name is None or topic_name.strip() == "":
            return ""
        topic = Topic.objects.get(lc_name = topic_name.lower())
        return '<a href="%s">%s</a>' % (topic.get_absolute_url(),topic_name)
    except Topic.DoesNotExist:
        return '<a href="%s" class="%s">%s</a>' % \
            (reverse('aswiki_topic', args = (topic_name,)),
             Topic.objects.css_class_name(topic_name), topic_name)

####################################################################
#
@register.simple_tag
def username_or_wikipage(user):
    """
    This is like 'user_wiki_page' except that if the user does not have a wiki
    topic set (whether it exists or not is not the same as not having one set)
    we will return a string of 'username (full name)'. If their full name is
    the empty string we will omit the '(full name)' part.

    Arguments:
    - `user`: The user object. If this is not a django.contrib.auth.models.User
              object we return ''.
    """
    if not isinstance(user, User):
        return ""

    topic_url = user_wikipage(user)
    if topic_url != "":
        return topic_url
    full_name = user.get_full_name().strip()
    if full_name != "":
        return "%s (%s)" % (user.username, full_name)
    return user.username
