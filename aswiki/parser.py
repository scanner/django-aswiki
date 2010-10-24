#
# File: $Id: parser.py 1865 2008-10-28 00:47:27Z scanner $
#
"""
This is where the logic and definition of our wiki markup parser lives.

We use the Python Creoleparser (which requires Genshi)

We make a custom dialect so that the parser can know the URL base for
all of the topics (pages) in the wiki and some additional goop so that
we can tell what other topics a given topic refers to.
"""

# system imports
#
from urllib import quote

try:
    import threading
except ImportError:
    import dummy_threading as threading

# Django imports
#
from django.core.urlresolvers import reverse
from django.utils.translation import ugettext as _

# 3rd party imports
#
from creoleparser.dialects import create_dialect, creole10_base, creole11_base
from creoleparser.core import Parser

from genshi import builder

# We see if we have the 'typogrify' app installed. If we do we will
# use it for rendering our templates to prettify them a bit.
#
try:
    from typogrify.templatetags.typogrify import typogrify
except ImportError:
    def typogrify(text):
        return text

# Model imports
#
from aswiki.models import Topic

############################################################################
############################################################################
#
class TopicList(object):
    """
    A helper class we use to keep track of all of the topics that are
    referenced by the raw content for a specific topic. We pass the
    objet and method instead 'path_fn' in to the 'path_func' parameter
    of our creole dialect we are goign to generate.

    The point of this class is that we need to know what topics are
    referenced by a specific topic when its content is created or
    modified. This lets us know that list of topics by their topic
    names.
    """

    ########################################################################
    #
    def __init__(self):
        """
        Very plain init. We set up the attribute for tracking topics.
        """

        # The list of topics that we have encountered while rendering
        # some content. This should be reset between renders.
        #
        self.topics = []

        # A dict mapping the lower case topic name to the original case used
        # in the text being parsed. This is so we can preserve the case
        # when doing things like creating nascent topics.
        #
        self.topics_case = { }

        # This is another list. It contains Topic's that we have
        # found this topic referring to not via [[wiki links]] but via
        # other methods like the <<subtopics >> macro. We need this so
        # that when we are done rendering we can find out what other topics
        # we should list in this topic's references.
        #
        self.extra_references = []

        # This is a bit of ugliness. Since we instantiate a TopicList and pass
        # a method when we create an instance of a Creole _dialect_ this one
        # instance will be shared across this process instance which may well
        # exist across multiple calls to render text via the parser generated
        # from the dialect, which means our list of topics will grow every
        # time we render a document.
        #
        # However, this is a problem since for our current use we only want
        # the topic names from rendering a single topic. So we have to make
        # sure no other thread of execution (if there are other threads
        # running.. if not this is a cheap operation.. XXX I think) modifies
        # the topic list we have to provide a mutex so only one thread at a
        # time can add topics to a topic list.
        #
        self.lock = threading.Lock()

    ########################################################################
    #
    def clear_and_lock(self):
        """
        Locks the mutex to prevent conflicts on updating the topic list if
        more then one thread tries to render using the same dialect instance
        at the same time.
        """
        self.lock.acquire()
        self.topics = []
        self.topics_case = { }
        self.extra_references = []
        return

    ########################################################################
    #
    def unlock(self):
        """
        Unlocks the mutex. Do NOT access the topics parameter after this is
        called. You can not be guaranteed whose list of topics you are seeing.
        """
        self.lock.release()
        return

    ########################################################################
    #
    def path_fn(self, topic_name):
        """
        This is called by our creole parser every time it encounters a
        wiki link in the text it is parsing. This lets us track which
        topics this text refers to.

        We are passed in a topic name, and we return that topic
        name.. if we were doing some sort of transformation on topic
        names this is where it would happen.
        Arguments:
        - `topic_name`: The topic name being referenced as a wiki link.
        """
        lower_topic_name = topic_name.lower()

        # if this is a topic name we have not seen yet, add it to our list
        # of topics.
        #
        if lower_topic_name not in self.topics:
            self.topics.append(lower_topic_name)
            self.topics_case[lower_topic_name] = topic_name

        return topic_name

############################################################################
#
def class_fn(topic_name):
    """
    This function is invoked by the markup dialect every time it encounters a
    wiki topic. It returns a string that is the css class name to add to wiki
    links as they are turned in to proper <a href></a> links.

    We use this as a way to annotate topics that do not exist yet with some
    graphical attribute so that users can easily tell which topics are not yet
    created.

    We use the wiki.models.TopicManager's css_class_name method to do this
    lookup.

    NOTE: Since this module is imported by the wiki.models module we need to
          import that module inside here so that we can access the Topic
          model. This is cheap since it will already be imported.

    Arguments:
    - `topic_name`: the topic name being checked for existence.
    """
    # XXX This is where we should do a cache lookup of the topic name
    #     and only if that fails fall back to
    #     Topic.objects.css_class_name(topic_name)
    #
    return Topic.objects.css_class_name(topic_name)

####################################################################
#
def output_mailto(arg_string):
    """
    Given the arguments of an anchor macro output the proper genshi
    stream that will render a mailto link. We also need to support the magic
    argument string format of '<you> AT <word> AT <foo> DOT <foo>'

    Arguments:
    - `arg_string`: The argument string of the anchor macro.
    - `macro_body`: The macro body if provided
    - `block_type`: True if this is a block macro.
    """
    # XXX Need to support the fancy format.. but for now just get the basic
    #     working.
    return builder.tag.a(arg_string, href="mailto:%s" % arg_string)

####################################################################
#
def output_subtopics(arg_string):
    """
    This will take a single string as its input. It will find all
    topics for which the string as a topic name is the parent topic.

    There is some semantic magic in a topic if it contains periods, ie: the
    '.' character. This forms a kind of hierarchy. Loosely speaking all topics
    that start with the same prefix, separated by '.' are sub-topics.

    So: 2007.Agenda is a sub-topic of 2007. 2007.Agenda.foo is a subtopic of
    2007 and 2007.Agenda.

    This macro will insert in to the output <ul> of the topics that are proper
    subtopics of the given string, ordered by name. So in the above example if
    I were to say <<subtopics 2007>> it would give me "2007.Agenda" and
    "2007.Agenda.foo" in a <ul>

    If the arg string ends with a dot, then it is treated as the
    separator. ie: <<subtopics 2007.>> and <<subtopics 2007>> are identical.

    Arguments:
    - `arg_string`: The topic we want to find all subtopics of.
    """
    arg_string = arg_string
    if arg_string[-1] != '.':
        arg_string = arg_string + "."

    topics = Topic.objects.filter(lc_name__istartswith = arg_string.lower()).order_by('lc_name')
    if topics.count() == 0:
        return None
    ul = builder.tag.ul()

    # For every topic that matches our pattern we insert a 'li' link
    # to that topic in our output. We also add this topic to the
    # 'extra_references' list in our global TOPIC_LIST object. This is
    # so that the prerender../save() methods of the Topic object we are
    # rendering this output for can know to add those topics to the list
    # of topics referenced by the topic being rendered.
    for topic in topics:
        TOPIC_LIST.extra_references.append(topic)
        ul.append(builder.tag.li(builder.tag.a(topic.name,
                                               href = topic.get_absolute_url())))
    return ul

####################################################################
#
def output_attachments(arg_string):
    """
    Returns a <ul> of all of the attachments attached to the topic name
    given as the arg_string.
    Arguments:
    - `arg_string`: Expected to be the name of a topic. If no such topic
                    exist, then no attachment list is generated.
    """
    try:
        topic = Topic.objects.get(lc_name = arg_string.lower())
    except Topic.DoesNotExist:
        return None
    ul = builder.tag.ul()

    # For every file attachment on this topic, add a 'li' link
    # to that attachment.
    #
    for attachment in topic.file_attachments.all():
        ul.append(builder.tag.li(builder.tag.a(attachment.basename(),
                                               href = attachment.get_absolute_url())))
    return ul

####################################################################
#
def macro_fn(name, arg_string, macro_body, block_type, environ):
    """
    Handles the macros we define for our version of markup.

    Arguments:
    - `name`: The name of the macro
    - `arg_string`: The argument string, including any delimiters
    - `macro_body`: The macro body, None for macro with no body.
    - `block_type`: True for block type macros.
    - `environ`   : The environment object, passed through from
                    creoleparser.core.Parser class's 'parse()' method.
    """
    name = name.strip().lower()
    arg_string = arg_string.strip()
    if name == 'anchor':
        if block_type:
            return builder.tag.a(macro_body, name = arg_string)
        else:
            return builder.tag.a(name = arg_string)
    elif name == 'mailto':
        return output_mailto(arg_string)
    elif name == 'gettext':
        if block_type:
            return _(macro_body)
        else:
            return _(arg_string)
    elif name == 'subtopics':
        return output_subtopics(arg_string)
    elif name == 'attachlist':
        return output_attachments(arg_string)
    elif name == 'attachment':
        # For including downloadable attachments in a wiki document.
        if block_type:
            return builder.tag.a(macro_body, href=arg_string)
        else:
            return builder.tag.a(arg_string, href=arg_string)
    return None

##
## Create our custom dialect. It will use our class function and a TopicList
## instance. The root URL for all wiki topics will be the same as the
## 'aswiki_topic_index' url.
##
## NOTE: This assumes that the url for a specific Topic is the same as the url
##       for the aswiki_topic_index with the Topic name appended to it
##
TOPIC_LIST = TopicList()

# dialect = creoleparser.dialects.Creole10(
#     wiki_links_base_url = reverse('aswiki_topic_index'),
#     wiki_links_space_char = '%20',
#     use_additions = True,
#     no_wiki_monospace = False,
#     wiki_links_class_func = class_fn,
#     wiki_links_path_func = TOPIC_LIST.path_fn,
#     macro_func = macro_fn,
#     interwiki_links_base_urls=dict(wikicreole='http://wikicreole.org/wiki/',
#                                    wikipedia='http://wikipedia.org/wiki/',)
#     )

dialect = Parser(dialect = create_dialect(\
        creole11_base, 
        wiki_links_base_url = reverse('aswiki_topic_index'), # NOTE: Make this
                                                             # a two element
                                                             # list for images
                                                             # to be loaded
                                                             # from a separate
                                                             # URL
        wiki_links_space_char = '%20', # NOTE: make this a two element list to
                                       # give images a different space
                                       # character.
        no_wiki_monospace = False,
        wiki_links_class_func = class_fn,
        wiki_links_path_func = TOPIC_LIST.path_fn, # NOTE: supports the list
                                                   # method where the second
                                                   # element of the list is
                                                   # used for images.
        bodied_macros = { },
        non_bodied_macros = { },
        macro_func = macro_fn,
        # custom_markup = (),
        interwiki_links_base_urls = {
            'wikicreole' : 'http://wikicreole.org/wiki/',
            'wikipedia'  :'http://wikipedia.org/wiki/' }
        ))
