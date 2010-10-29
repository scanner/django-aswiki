#
# File: $Id: models.py 1857 2008-10-26 00:24:51Z scanner $
#

# Python standard lib imports
#
import datetime
import pytz
import os.path
import re
from urllib import quote, unquote

# Django imports
#
from django.db import models
from django.conf import settings
from django.db.models import permalink
from django.utils.translation import ugettext_lazy as _
import django.dispatch
from django.core.files.storage import FileSystemStorage

# 3rd party module imports
#
import tagging
import creoleparser

# We see if we have the 'typogrify' app installed. If we do we will
# use it for rendering our templates to prettify them a bit.
#
try:
    from typogrify.templatetags.typogrify import typogrify
except ImportError:
    def typogrify(text):
        return text

# If the django-notification app is present then import and we will use this
# instead of sending email directly.
#
if "notification" in settings.INSTALLED_APPS:
    import notification
else:
    notification = None

# favour django-mailer but fall back to django.core.mail
try:
    from mailer import send_mail
except ImportError:
    from django.core.mail import send_mail

# Model imports
#
from django.contrib.auth.models import User
from django.contrib.sites.models import Site

# We need to set datetimes here and there. Django's rules are that we store
# times in the database in the configured timezone in settings. Since
# we refer to things in UTC we need to properly convert our datetimes before
# storing. So, we load up in to a variable we can use in this module
# the tzinfo of the django server's timezone. We also define a function
# that makes this conversion a little easier to see inline.
#
dj_tzinfo = pytz.timezone(settings.TIME_ZONE)

def servertime(dt):
    """
    Convert a datetime passed in that may be naieve but is assumed to be in
    UTC to the server's timezone and return that.
    """
    return dt.replace(tzinfo = pytz.UTC).astimezone(dj_tzinfo)

# Because aswiki serves up content for attachments and images and because these
# bits of content may be restricted by permissions we can not have these
# uploaded files sitting under MEDIA_ROOT. If they were someone could retrieve
# them if they knew the path name without going through our permission system
# at all. This is bad, even though serving them up ourselves is expensive I do
# not see where we have a choice as for some people the content may be
# sensitive. We create our own FileSystemStorage object that points at this
# location. Of course, if the setting for ASWIKI_UPLOAD_ROOT was not set, then
# we fall back to MEDIA_ROOT.
#
fs = FileSystemStorage(location = getattr(settings, "ASWIKI_UPLOAD_ROOT",
                                          os.path.join(settings.MEDIA_ROOT,
                                                       'aswiki')))

# We define a signal that is invoked whenever Topic is renamed.
# This is what the aswiki app uses to know to go through all of the
# topics that a renamed topic is referenced by and modify their content
# so that the wiki links in the raw and formatted content still work.
#
# The sender will be the topic that has been renamed.
#
topic_renamed = django.dispatch.Signal(providing_args = ['old_name'])

# We define a signal that is invoked whenever a Topic is deleted.
# This is important because we want to separate the logic that
# de-links references that any given Topic has to another Topic. If a
# Topic is marked as deleted then any other Topic that references this
# Topic has to have that linkage broken. What is more, in those other
# Topics if we pre-render content then we need to make sure that the
# pre-rendered content properly reflects that this Topic no longer
# exists.
#
# The sender will be the topic that has been deleted.
#
topic_deleted = django.dispatch.Signal()

# We define a signal that is invoked whenever a Topic's content is modified.
# If this Topic's content has added or removed links to other Topics in this
# wiki then we need to update the list of Topics we reference.
#
topic_modified = django.dispatch.Signal(providing_args = ['trivial_change'])

# We define a signal that is raised if a topic has changed in such a way that
# interested users should be notified of the change.
#
# NOTE: This is mostly to hook in to the 'notification' app if it is available
#       This will be raised on a sub-set of 'topic_modified' signals if the
#       change is not considered 'trivial' by the user making the change.
#
topic_notify = django.dispatch.Signal()

# We define a signal that is invoked whenever a topic is created. This is
# primarily intended to let some other process handle the work of
# formatting the content and resolving the links on any other topics
# that referreed to this topic by name before this topic was created.
#
topic_created = django.dispatch.Signal()

# Topic versions are specified by their creation timestamp.  We have a
# normalized version of this timestamp. This is the strftime/strptime
# format string for that normalized version.
#
NORM_TIMESTAMP='%Y-%m-%d_%H:%M:%S'

# XXX HACK - this defines a regular expression that will match strings
#     in our raw content that refer to wiki links. This lets us find
#     said bits in our content and replace them when we have to go to
#     topics that have references to a topic that has been renamed.
#
WIKILINK_RE = re.compile(r'\[\[([^\]|]+)(\]\]|\|)', re.I)

# When a topic is being edited, renamed, or deleted it will be
# held by a write lock that prevents, well, at least warns, other users
# that they can not tamper with that topic until the lock is released.
#
# This sets the time limit for how long a write lock will be held. If a user
# does nothing the lock will expire in this many minutes.
#
WRITE_LOCK_EXPIRY = datetime.timedelta(minutes = 20)

####################################################################
#
# We have several exceptions that manipulations of Topics can raise.
#
class TopicException(Exception):
    def __init__(self, value = "TopicException"):
        self.value = value
    def __str__(self):
        return "TopicException: %s" % self.value

####################################################################
#
class TopicExists(TopicException):
    """
    Raised when a user tries to create a topic with the same name as
    an undeleted topic that already exists.
    """
    def __init__(self, value = "Topic already exists"):
        self.value = value
    def __str__(self):
        return "TopicExists: %s" % self.value

####################################################################
#
class PermissionDenied(TopicException):
    """
    Some topics have permissions or are in a state (such as being
    locked) that disallow them from being modified by a certain set of
    users.
    """
    def __init__(self, value = "Permission denied"):
        self.value = value
    def __str__(self):
        return "PermissionDenied: %s" % self.value

####################################################################
#
class BadName(TopicException):
    """
    Raised when a user tries to create a topic with the a name that
    has characters we do not allow in it (to the point: "/" is bad.)
    """
    def __init__(self, value = "Topic name has characters in it thare "
                 "not allowed."):
        self.value = value
    def __str__(self):
        return "BadName: %s" % self.value

####################################################################
#
class NascentTopic(models.Model):
    """
    A NascentTopic is a topic that some set of Topics has references
    to in their content field, but itself does not exist.

    The purpose of this model is two-fold: one, so that when a new
    topic is created we can tell if any topics were referring to this
    topic before it was created - we use this to re-render those
    topics so their references and rendered content are all
    proper. Secondly, it is convenient to have a way to easily list
    all the topics that someone, somewhere is referring to that has
    not been created yet. This would let busy bodies go and create
    them.  Also we can find potentially broken topic names this way
    (if some one had [[foobar]] and somewhere later had [[foo bar]] we
    may want to know about these and fix them if they should be
    referring to the same topic.

    NOTE: When a topic is created, if a nascent topic exists with the
    same name, after all of the references have been cleaned up the
    nascent topic needs to be deleted (and all the topics that
    referred to the nascent topic need to be re-rendered.)
    """

    name = models.CharField(_('name'), max_length = 128, db_index = True,
                            unique = True)
    lc_name = models.CharField(_('lower case name'), max_length = 128,
                               db_index = True, unique = True,
                               default = '')
    created = models.DateTimeField(_('created'), auto_now_add = True,
                                   help_text = _('The time at which '
                                                 'this topic was originally '
                                                 'created.'))
    author = models.ForeignKey(User, verbose_name = _('author'),
                               help_text = _('The author is the first '
                                             'person to refer to this topic.'))

    class Meta:
        ordering = ("name", "-created")

    ####################################################################
    #
    def save(self, *args, **kwargs):
        """
        We override the inherited save method so that we can ensure
        that the lc_name is always filled in and is always correct.
        """
        self.lc_name = self.name.lower()

        # Make sure they are not using a topic name that has "/" or ":" in it.
        #
        if not Topic.valid_name(self.name):
            return

        super(NascentTopic, self).save(*args, **kwargs)
        return

    ####################################################################
    #
    def __unicode__(self):
        return u"%s" % self.name

####################################################################
#
#class CaseInsensitiveQuerySet(QuerySet):
#    """
#    This is cribbed from: http://www.djangosnippets.org/snippets/305/
#    """
#    def _filter_or_exclude(self, mapper, *args, **kwargs):
#        # 'name' is a field in your Model whose lookups you want
#        # case-insensitive by default
#        #
#        if 'name' in kwargs:
#            kwargs['name__iexact'] = kwargs['name']
#            del kwargs['name']
#        return super(CaseInsensitiveQuerySet, self)._filter_or_exclude(mapper, *args, **kwargs)

##################################################################
##################################################################
#
class WriteLock(models.Model):
    """
    A write lock is an object that when related to a Topic indicates
    that a user is currently editing that topic.

    A WriteLock contains a reference to the user that has the
    WriteLock and a datetime after which the WriteLock is
    automatically released. ie: if you attempt to edit a Topic that
    has a WriteLock held by a different user.. however that
    WriteLock's expiry time is in the past, you can assume ownership
    of the WriteLock, and its expiry time will be extended.

    XXX This can still lead to a race condition if two users attempt
        to establish a write lock at the same time. We should use some
        database locking primitive when we are establishing a
        WriteLock.
    """
    owner = models.ForeignKey(User, verbose_name = _('owner'),
                               help_text = _('The owner of this WriteLock.'))
    expiry = models.DateTimeField(_('expiry'),
                                  help_text = _('The time at which this '
                                                 'WriteLock will expire..'))

    class Meta:
        ordering = ("expiry",)

    ####################################################################
    #
    def __unicode__(self):
        return _("WriteLock held by %s will expire at %s") % \
            (self.owner.username, self.expiry)

####################################################################
#
class TopicManager(models.Manager):
    """
    In our set of all topics we have ones that are marked as 'deleted'
    We want by the default manager to automatically filter out 'deleted'
    items.
    """
    ####################################################################
    #
    def get_query_set(self):
        """
        Return a query set of all of the topics that are NOT deleted,
        and searches for 'name' are by default case insensitive.  This
        lets us provide default views of topics that do not show
        deleted topics.
        """
        return super(TopicManager,self).get_query_set().filter(deleted = False)

    ####################################################################
    #
    def css_class_name(self, name):
        """
        This is a convenience function that will return a string
        intended to be used for a CSS class name for wiki links. The
        primary use is for being able to mark up topics being used as
        wiki links that do not exist yet (or perhaps are deleted.)

        XXX Right now this only returns the string 'nonexistent' if the
            given topic does not exist (or is deleted.) I thought about
            using the string 'doesnotexist' but that is harder to read.

            Otherwise we return None.

            We should probably have it return something like 'ronly'
            if it is locked and 'noread' or something if you do not
            have permission to view it.

        NOTE: We lower case all topic names because we only allow
              lowercase topic names (although maybe we should change
              this so that we instead do case insensitive name
              matches.)

        XXX We should REALLY REALLY use a caching system to cache
            topics that are found. This will avoid db lookups for
            topics we encounter frequently.

        Arguments:
        - `name`: The name of the topic we want the css class for.
        """
        if self.get_query_set().filter(name__iexact = name).count() == 0:
            return 'nonexistent'
        return None

####################################################################
#
class Topic(models.Model):
    """The core of the aswiki app is the 'Topic.' This represents a
    single wiki topic. It can be referred to by its name, or its
    id. It is versioned so as topics are updated people can access the
    older versions of that topic.

    # In order to test topics we need a user.
    #
    >>> from aswiki.models import Topic
    >>> from django.contrib.auth.models import User
    >>> u = User(username='test',email = 'test@no.where')
    >>> u.save()
    >>> t1 = Topic(name="topic1", author = u, content_raw = 'test points at [[test]]')
    >>> t1.save()
    >>> t1.content_raw
    'test points at [[test]]'
    >>> t1.content_formatted
    '<p>test points at <a href="/wiki/topic/test">test</a></p>\n'
    >>> t1.references.all()
    [<Topic: test>]
    >>> t1.referenced_by.all()
    []
    # By default every is permitted to read and edit topics.
    #
    >>> t1.permitted(u)
    True

    # Let us make a new topic to test cross topic linking.
    #
    >>> t2 = Topic(name="topic2", author = u, content_raw = 't2 points at [[topic1]] and [[test]] and itself [[topic2]]')
    >>> t2.save()
    >>> t2.content_formatted
    '<p>t2 points at <a href="/wiki/topic/topic1">topic1</a> and <a href="/wiki/topic/test">test</a> and itself <a href="/wiki/topic/topic2">topic2</a></p>\n'
    >>> t2.references.all()
    []
    >>> t2.referenced_by.all()
    []
    >>> t1.references.all()
    []
    >>> t1.referenced_by.all()
    []

    # And renaming..
    #
    >>> t1.rename(u, "new_topic1")
    >>> t1.referenced_by.all()
    []
    >>> t2.references.all()
    []
    >>> t2.content_raw
    ''
    >>> t2.content_formatted
    ''

    # Now let us update topic1 so that it also has a link to topic2.
    #
    >>> t1.update_content(u, t1.content_raw + " and a link to [[topic2]]")
    >>> t1.content_raw
    ''
    >>> t1.content_formatted
    ''
    >>> t1.references.all()
    []
    >>> t2.referenced_by.all()
    ''
    # It will now have a new topic version.
    #
    >>> t1.topicversion_set.all()
    []
    # and the content of this version will be our old raw content.
    #
    >>> t1_v = t1.topicversion_set.all()[0]
    >>> t1_v.content_raw
    ''
    # Now we delete topic2..
    #
    >>> t2.mark_as_deleted(u)
    >>> t1 = Topic.objects.get(name='new_topic1')
    >>> t1.content_formatted
    ''
    # And in the list of all topics there should be no topic2.
    #
    >>> Topic.objects.all()
    []
    """
    # The default manager people will see has the deleted topics
    # filtered out.
    #
    objects = TopicManager()
    default_manager = models.Manager()

    # NOTE: There can only be one topic at a time that is not deleted
    #       with the same name. This is also where there is no 'create'
    #       view. When you go to a url, if there is no topic with that
    #       name (that is not deleted) it will let you create that topic.
    #
    name = models.CharField(_('name'), max_length = 128, db_index = True)

    # NOTE: The lower case name is needed so that we can case-preserve topic
    #       names and still efficiently look up a whole set of topics using
    #       the 'in' keyword.
    lc_name = models.CharField(_('lower case name'), max_length = 128,
                               db_index = True, default = '')
    created = models.DateTimeField(_('created'), auto_now_add = True,
                                   help_text = _('The time at which '
                                                 'this topic was originally '
                                                 'created.'))
    modified = models.DateTimeField(_('modified'), db_index = True,
                                    help_text = _('The timestamp of the last '
                                                  'edit of this topic.'))
    author = models.ForeignKey(User, verbose_name = _('author'),
                               help_text = _('The author is the last '
                                             'person to update this topic.'))
    content_raw = models.TextField(_('content raw'), blank = True)
    content_formatted = models.TextField(_('content formatted'), blank = True)
    write_lock = models.OneToOneField(WriteLock, verbose_name = _('write lock'),
                                      null = True,
                                      help_text = _('Another user currently '
                                                    'has the topic temporarily '
                                                    'locked for editing.'))
    locked = models.BooleanField(_('locked'), default = False, help_text =
                                 _('A locked topic can only be modified by '
                                   'a moderator.'))
    restricted = models.BooleanField(_('restricted'), default = False,
                                       help_text = _('A restricted topic '
                                                     'requires that you have '
                                                     'explicit "restricted" '
                                                     'permission to read or '
                                                     'edit this topic.'))
    deleted = models.BooleanField(_('deleted', default = False, help_text =
                                    _('If this topic has been deleted, it is '
                                      'still around, just not easily '
                                      'accessible')))

    # We keep explicit track of all topics that a given topic references.
    # This is mostly so that we can deal with renaming of topics, but it is
    # also handy in that it lets a topic know and display to the user what
    # topics reference this one.
    #
    references = models.ManyToManyField('self', verbose_name = _('references'),
                                        help_text = _('Other topics that this '
                                                      'topic has links to.'),
                                        related_name = 'referenced_by',
                                        symmetrical = False)

    # We also keep a list of all topics that are referred to by this topic
    # that do NOT exist yet.
    #
    nascent_topics = models.ManyToManyField(NascentTopic, null = True,
                                            verbose_name = _('nascent topics'),
                                            help_text = _('topics that do not '
                                                          'exist yet that '
                                                          'this topic refers '
                                                          'to'))

    # When you are looking at a topic and what some human string about why
    # this topic is different then its previous version this is a place
    # for that hint.
    #
    reason = models.CharField(_('reason'), blank = True, max_length = 256,
                              help_text = _('A short blurb giving the reason '
                                            'for updating a topic. It can be '
                                            'blank'))
    class Meta:
        ordering = ("-modified",)
        permissions = (("restricted", "Can read/edit a restricted topic"),
                       ("lock_topic", "Can lock/unlock a topic" ))

    ####################################################################
    #
    def __unicode__(self):
        return u"%s" % self.name

    ##################################################################
    #
    def write_locked(self):
        """
        A quick check to tell if a topic is write locked or not. Checks
        the expiry time on a write lock if it exists. Handy for use in
        templates.
        """
        if self.write_lock is None or \
                self.write_lock.expiry < datetime.datetime.utcnow():
            return False
        return True

    ##################################################################
    #
    def get_write_lock(self, user, force = False):
        """
        Attempt to obtain the write lock for this topic by this user.
        If we manage to obtain a write lock we return True, else we
        return False.

        If a write lock exists and it is owned by this user and it is
        about to expire, its expiry will be extended.

        If a write lock exists and it is not owned by this user, but
        it has expired then the write lock will be changed to this
        user and its expiry reset.

        If a write lock exists and it is not owned by this user and it
        has not expired, then 'False' is returned.

        If 'force' is True, then even if there is a write lock owned
        by another user and it has not expired, it will be changed to
        be owned by this user.

        XXX I believe that there are race conditions in the current
            system where write locks can be created and never deleted
            and no longer associated with any topic, thus creating
            orphaned write locks. Perhaps we should move back to
            OneToMany relationship where many write locks can refer to
            a topic (but the topic will only have one write lock) so
            that we can delete orphaned write locks pro-actively.

        Arguments:
        - `user`: The user that is trying to obtain the write lock.
        - `force`: To force ownership of the write lock if it exists to
                   this user.
        """
        if self.write_lock is None:
            # This topic has no write lock. Create one, assign it to this
            # topic.
            #
            wl = WriteLock(owner = user,
                           expiry = datetime.datetime.utcnow() + \
                               WRITE_LOCK_EXPIRY)
            wl.save()
            self.write_lock = wl
            self.save(render = False)
            return True

        # This topic has a write lock already. See if it belongs to
        # this user.
        #
        now = datetime.datetime.utcnow()
        if self.write_lock.owner == user:
            # If there are less then 5 minutes left in the write lock, extend
            # it.
            #
            if (self.write_lock.expiry - now) < datetime.timedelta(minutes = 1):
                self.write_lock.expiry = datetime.datetime.utcnow() + \
                    WRITE_LOCK_EXPIRY
                self.write_lock.save()
            return True

        # A write lock exists, but it is not owned by this user. If it
        # has expired, then change the owner to this user and re-set
        # its expiry time
        #
        if self.write_lock.expiry < now or force:
            # Hey, it has expired, or we forcing it to change ownership.
            # Change the owner and reset the expiry time.
            #
            self.write_lock.owner = user
            self.write_lock.expiry = now + WRITE_LOCK_EXPIRY
            self.write_lock.save()
            return True

        # If we get here the topic is write locked, and the write lock
        # has not expired.
        #
        return False

    ##################################################################
    #
    def release_write_lock(self, user, force = False):
        """
        Releases the write lock on this topic.

        If there is no write lock, nothing happen, and we return True.

        If there is a write lock, and it is expired, then it is
        deleted and we return True

        If there is a write lock, held by this user, then it is
        deleted and we return True.

        If there is a write lock, and it is NOT held by this user, and
        it is NOT expired, then nothing is done and we return False.

        If there is a write lock, and it is NOT held by this user, and
        itis NOT expried, but 'force' is set to True, then it is
        deleted and we return True.

        Arguments:
        - `user`:
        """
        # No write lock.. nothing to delete.
        #
        if self.write_lock is None:
            return True

        # Write lock is owned by this user.. just delete it.
        #
        if self.write_lock.owner == user:
            wl = self.write_lock
            self.write_lock = None
            self.save()
            wl.delete()
            return True

        # Okay, write lock exists and is NOT owned by this user. They
        # can only delete it if it is expired or force == True.
        #
        now = datetime.datetime.utcnow()
        if force or self.write_lock.expiry < now:
            wl = self.write_lock
            self.write_lock = None
            self.save()
            wl.delete()
            return True

        # Otherwise this write lock could not be deleted.
        #
        return False
    
    ##################################################################
    #
    def permitted(self, user):
        """
        A boolean helper method. Determines if the user has permission
        to read this topic or not.

        Basically we let any authenticated user read or modify an
        existing topic UNLESS the topic has its 'restricted' bit
        set. If it does, then the user must have the 'restricted'
        permission to read or modify this topic.

        NOTE: If the user passed in has the django_granular_permission
              attribute 'has_row_perm' and that is checked if the user
              does not have the module level restricted permission.

        Arguments:
        - `user`: The user object that we want to check read permissions for.
        """
        if not self.restricted:
            return True

        # This topic is restricted. They must have the 'restricted' permission
        #
        if not user.is_authenticated:
            return False

        # See if they have either module permission or the row level permission
        #
        if user.has_perm('aswiki.restricted') or \
                getattr(user, 'has_row_perm', lambda x,y: False)(self, 'restricted'):
            return True
        return False

    ####################################################################
    #
    def save(self, render = True, notify = False, *args, **kwargs):
        """
        We override the inherited save method. We need to send a
        'topic_created' signal when we create a topic. This lets a
        handler update all topic that had a reference to the
        not-yet-created topic up their rendered content to reflect
        that the link to the newly created topic actually exists.

        NOTE: Topic name's must be lower case so we force it to lower
              case here in case it was not.

        Arguments:
        - `render`: - Should we actually render the content_raw in to
                      content_formatted. This should be set to false if
                      our caller has already pre-rendered the content for us.
        - `notify`: - If true then we will find if there are any watches on
                      this topic and send out notifications that the topic
                      has changed. This defaults to 'false' so that various
                      inadverdant saves do not trigger a notificaiton.
        """
        self.lc_name = self.name.lower()

        # Make sure modified is filled in. We only set this if it is not
        # already set.
        #
        if self.modified is None:
            self.modified = servertime(datetime.datetime.utcnow())

        # Make sure they are not using a topic name that has "/" or "." in it.
        #
        if not Topic.valid_name(self.name):
            raise BadName("'/' and ':' characters are not allowed in topic "
                          " names. Use '.' if you want to create a "
                          "hierarchy of topics.")

        if self.id is None:
            # Several things need to happen when a topic is created, but
            # for the most part they have to happen after the object
            # has been saved to the disk at least once (rendering relies
            # upon this due to foreign key relationships in the model)
            #
            # However, we can pre-render the content and have the formatted
            # version saved to the db.
            new = True
            if render:
                self.prerender_content(update_relationships = False)

        else:
            # Ah, this object exists in the database already, then we can
            # pre-render the content and update foreign key relationships
            # before we save our modified content to the db.
            #
            new = False
            if render:
                self.prerender_content()

        super(Topic, self).save(*args, **kwargs)

        if new:
            # This call to pre-render content will update all of our
            # relationships.
            #
            if render:
                self.prerender_content()

                # B-( we have to save it again, because it may be
                # referring to itself and this will leave the rendered
                # content thinking that the link to itself as a topic
                # does not exist.
                #
                super(Topic, self).save(*args, **kwargs)

            # If this is a new topic we need to send a signal so that
            # various things that happen when a new topic is created are
            # done.
            #
            topic_created.send(self)
        return

    ####################################################################
    #
    def prerender_content(self, update_relationships = True):
        """
        A helper method. When a Topic's content needs to be
        re-rendered this method does that work. It will take the raw
        content and pass it through our creole parser. It will then
        make sure that the list of topics that this topic references
        is updated.

        NOTE: This does NOT save() the topic after we re-render the content.

        Arguments:
        - `update_relationships`: - this indicates if we should also update the
                                    relationships to other topics and to
                                    nascent topics.  The only time this would
                                    be called with 'False' would be in our own
                                    `save()` method because the foreign
                                    relationships can not be updated until we
                                    have been saved to the database at least
                                    once. This lets us save the formatted
                                    content to the database, and then do
                                    operations that do not require a
                                    'save()'. The downside is it means we
                                    render the content twice. Hopefully the
                                    expense of that will be reasonable.
        """

        # XXX To avoid circular dependencies since aswiki.parser imports
        #     aswiki.models.Topic. Luckily this is a fairly cheap operation
        #     as the module will already be loaded and this just puts it
        #     in the namespace of this function.
        #
        from  aswiki.parser import parser, TOPIC_LIST

        # Due to the global nature of aswiki.parser.dialect we need to lock
        # and clear our list of topics it finds when rendering, we must then
        # copy that list and unlock the global TOPIC_LIST.
        #
        try:
            TOPIC_LIST.clear_and_lock()
            TOPIC_LIST.current_topic = self.name
            self.content_formatted = typogrify(\
                parser.render(self.content_raw,
                              environ = TOPIC_LIST))
            topics = set(TOPIC_LIST.topics)
            topics_case = dict(TOPIC_LIST.topics_case)
            extra_references = list(TOPIC_LIST.extra_references)
        finally:
            TOPIC_LIST.current_topic = None
            TOPIC_LIST.unlock()

        # If any topic in the topics list is not a valid name we need
        # to raise an exception
        #
        for t in topics:
            if not Topic.valid_name(t):
                raise BadName("The topic '%s' is not a valid topic name. "
                              "Topic names must not contain ':' or '/'. "
                              "Use '.' if you want to create a "
                              "hierarchy of topics." % t)

        # Only update all of our topic and nascent topic references
        # if the flag to do so is true.
        #
        if not update_relationships:
            return

        # Now we go through the list of topics this topic references
        # adding them to the 'references' attribute.
        #
        # Also, if there were any extra topic references we retrieved
        # from the TOPIC_LIST, add them in as well.
        #
        references = Topic.objects.filter(lc_name__in = topics)
        self.references = list(references) + extra_references

        # We also need to add references to any nascent topics that
        # exist that we refer to.
        #
        exists = set([x.name.lower() for x in references])
        does_not_exist = topics - exists
        nascent = NascentTopic.objects.filter(lc_name__in = does_not_exist)
        self.nascent_topics = nascent
        nascent = set([x.name.lower() for x in nascent])

        # If we refer to any nascent topics that do not exist we need
        # to create them and add references to them. Be sure to create
        # them with the original case they were referred to.
        #
        does_not_exist = does_not_exist - set(nascent)
        for topic in does_not_exist:
            self.nascent_topics.create(name = topics_case[topic],
                                       lc_name = topic.lower(),
                                       author = self.author)
        return

    ####################################################################
    #
    def rename_referenced_topic(self, old_name, new_name):
        """
        When a Topic, let us call it `B` is renamed from `old_name` to
        `new_name`, all topics which referenced `B` in their raw
        content need to have their raw content updated so that their
        references to topic `B` by name are changed to the new name
        for `B`, and then re-rendered (which is done automatically
        upon saving).

        By re-rendering the topic all of its references to other
        topics will be straightened out as well - provided that the
        content_raw was properly updated.

        Arguments:
        - `old_name`: The old topic name we have a reference to.
        - `new_name`: The new topic name to use in its place
        """

        # XXX Here we are doing the nasty thing - since I can not find
        #     any reasonable way to do this via the creoleparser itself
        #     I have to know how the wiki links are formatted and search
        #     for them with a regular expression so that I can replace
        #     one name with another. Do not like this. I think I can actually
        #     have creole's parser do this by getting things out of the
        #     by subclassing and replacing the 'generate' method or something.
        #     But for now this works.
        #
        # XXX We are really simplistic.. this will catch even cases that would
        #     would not be rendered as wiki links. I am going to say that is
        #     okay for now. When we take on creoleparser subclasses then
        #     we can do this properly.
        old_name = old_name.lower()

        def repl(matchobj):
            """
            A helper function that will replace a match if it is the
            one being renamed.

            Arguments:
            - `matchobj`: a regular expression match object.
            """
            if matchobj.group(1).lower() == old_name:
                return "[[" + new_name + matchobj.group(2)
            return matchobj.group(0)

        self.content_raw = WIKILINK_RE.sub(repl, self.content_raw)
        self.save()
        return

    ####################################################################
    #
    def _new_version(self, user, reason = None):
        """
        A helper method that will create a new TopicVersion of this topic.

        Arguments:
        - `user`: The user making the modification that is causing us to
                  version this topic.
        - `reason`: The topic's reason will be set to this after the new
                    TopicVersion is created.
        """
        tv = TopicVersion(topic = self, author = self.author, name = self.name,
                          content_raw = self.content_raw,
                          reason = self.reason, created = self.modified,
                          normalized_created = self.modified.strftime(NORM_TIMESTAMP))
        tv.save()
        self.reason = reason
        self.author = user
        return

    ####################################################################
    #
    def update_content(self, user, new_content, reason = None,
                       update_modified = True, trivial = False):
        """
        This is the method you are supposed to invoke if the content
        of a topic is being modified. It will do the work to set the
        content_raw and content_formatted properly.

        NOTE: Since the content is being changed it will also go
              through the content and determine what topics this topic
              references and update the 'references' attribute as
              well.

        NOTE: This will create a new TopicVersion of the current
              topic's contents first. The `modified` and `author` attributes
              of the topic will be updated.

        Arguments:
        - `new_content`: The new content this topic is being updated with.
        - `user`: The user that is making this change.
        - `reason`: The reason the content was modified. If not provided a
                    fairly generic reason will be used.
        - `update_modified`: By default updating the content updates the
                             'modified' timestamp of the topic. In some cases
                             we do not want that to happen. Settings this
                             parameter to true will cause the modified
                             timestamp to not be set.
        """
        # XXX This is probably where we should check if the user has permission
        #     to update this topic if we were to have topic modify permissions
        #
        if self.locked and not user.is_staff:
            raise PermissionDenied(_("Topic `%s` is locked.") % self.name)

        if reason is None or len(reason) == 0:
            reason = _('Topic "%s" edited by %s') % (self.name, user.username)
        self._new_version(user, reason)
        self.content_raw = new_content
        if update_modified:
            self.modified = servertime(datetime.datetime.utcnow())
        self.save()

        # We send topic modified on any content change..
        #
        topic_modified.send(sender = self, trivial_change = trivial)

        # We only send notifies on non-trivial changes.
        #
        if not trivial:
            topic_notify.send(sender = self)
        return

    ####################################################################
    #
    def revert(self, user, topic_version, reason):
        """
        Does the work of reverting this topic to that of a previous version.

        NOTE: This will call 'self.update_content()' to do the actual
              work.

        Arguments:
        - `user`: The user doing the reversion.
        - `topic_version`: The TopicVersion instance to revert to. This
                           TopicInstance must be a version of this Topic.
        - `reason`: The reason for the reversion.
        """
        if topic_version.topic != self:
            raise TopicException(_("'%s' is not a version of topic '%s'") % \
                                     unicode(topic_version), self.name)
        if reason is None:
            reason = _('Topic "%s" being reverted to version %s by %s') % \
                (self.name, topic_version.normalized_created, user.username)
        self.update_content(user, topic_version.content_raw, reason)

    ####################################################################
    #
    def mark_as_deleted(self, user, reason = None):
        """
        Marks a topic as deleted. This will cause a new version of this topic
        to be created, and the 'deleted' attribute will be set to True.

        NOTE: This will 'save()' the object after marking it as deleted.

        Arguments:
        - `user`: The user deleting this Topic
        - `reason`: The reason for deleting this Topic
        """
        if self.locked and not user.is_staff:
            raise PermissionDenied(_("Topic `%s` is locked.") % self.name)

        if reason is None:
            reason = _('Topic "%s" deleted by %s') % (self.name, user.username)

        self._new_version(user, reason)
        self.deleted = True
        self.modified = servertime(datetime.datetime.utcnow())
        self.save()
        topic_deleted.send(sender = self)
        return

    ####################################################################
    #
    def rename(self, user, new_name, reason = None):
        """
        The process of renaming a topic is pretty heavy. We need to go
        through all topics that have this topic's name embedded in
        their content and change those links as well. Ideally this is
        done by some other processes that listens to the 'topic
        renamed' signal.

        Basically we make sure that the new topic name is not in use.
        We version the current topic, set the name to the new name,
        and then save the topic.

        If the topic already exists a TopicExists exception will be raised.

        NOTE: This will create a new TopicVersion of the current
              topic's contents first. The `modified` and `author` attributes
              of the topic will be updated.

        NOTE: After we have saved the topic we fire off the
              topic_changed signal.

        Arguments:
        - `new_name`: The new name to change the topic to.
        - `user`: The user renaming this topic.
        - `reason`: An optional short string describing the reason for renaming
                    the topic.
        """
        if self.locked and not user.is_staff:
            raise PermissionDenied(_("Topic `%s` is locked.") % self.name)

        if Topic.objects.filter(name=new_name).count() != 0:
            raise TopicExists

        # Create a new TopicVersion based on this topic.
        #
        if reason is None:
            reason = _('topic renamed from "%s" to "%s" by %s') \
                % (self.name, new_name, user.username)

        old_name = self.name
        self._new_version(user, reason)
        self.name = new_name
        self.modified = servertime(datetime.datetime.utcnow())
        self.save()
        topic_renamed.send(sender = self, old_name = old_name)
        return

    ##################################################################
    #
    @classmethod
    def valid_name(cls, name):
        """
        Is the given name a valid name for a topic. We do not allow
        certain characters in our topic name.

        Returns 'True' if name is acceptable, 'False' otherwise.
        
        XXX In the future we should probably reencode forbidden
            characters so that we allow them but they do not cause
            problems.

        Arguments:
        - `name`: The topic name to check.
        """
        if "/" in name or ":" in name:
            return False
        return True
    
    ####################################################################
    #
    @permalink
    def get_absolute_url(self):
        """
        The URL of a topic is always by its name. This is the simplest
        representation that also delivers a URL that people expect.

        XXX However, this has flaws in that if a topic's name changes
            then the URL to reach it has also changed. I keep
            wondering if we should have a 'by name' url and a more
            traditional 'by id' url. Although have two url's that
            refer to the same exact object has other problems.

        """
        return ("aswiki_topic", [self.name])

# We register the Topic model with the tagging module - this gives
# all of our Topic's the ability to have tags.
#
tagging.register(Topic)

##################################################################
##################################################################
#
def attachment_dir(instance, filename):
    """
    A helper method for the 'attachment' attribute of the
    FileAttachment model. We want file attachments to be stored under
    a directory defined by the topic they are being attached to.

    Arguments:
    - `instance`: FileAttachment instance object.
    - `filename`: original file name being uploaded.
    """
    return os.path.join("files", instance.topic.name, filename)

class FileAttachment(models.Model):
    """
    Topics can have a number of files attached to them that people
    can download. This object represents a single attachment.

    It is mostly just a thin wrapper around a FileField.
    """
    topic = models.ForeignKey(Topic, verbose_name = _('topic'),
                              db_index = True, editable = False,
                              help_text = _('The topic this attachment '
                                            'belongs to.'),
                              related_name = 'file_attachments')
    created = models.DateTimeField(_('created'), auto_now_add = True,
                                   editable = False,
                                   help_text = _('The time at which '
                                                 'this file was '
                                                 'originally uploaded.'))
    attachment = models.FileField(_('attachment'), max_length = 256,
                                  storage = fs, db_index = True,
                                  upload_to = attachment_dir)
    owner = models.ForeignKey(User, verbose_name = _('owner'),
                              editable = False,
                              help_text = _('The user that uploaded this '
                                            'file.'))

    ##################################################################
    #
    def __unicode__(self):
        return "<Attachment %s on topic '%s'>" % (self.attachment,
                                                  self.topic.name)

    ##################################################################
    #
    def basename(self):
        return os.path.basename(self.attachment.name)

    ##################################################################
    #
    @permalink
    def get_absolute_url(self):
        return ('aswiki_topic_attachment', (self.topic.name, self.basename()))

##################################################################
##################################################################
#
def image_dir(instance, filename):
    """
    A helper method for the 'image' attribute of the
    ImageAttachment model. We want images to be stored under
    a directory defined by the topic they are being attached to.

    Arguments:
    - `instance`: ImageAttachment instance object.
    - `filename`: original file name being uploaded.
    """
    return os.path.join("images", instance.topic.name, filename)

class ImageAttachment(models.Model):
    """
    Like the FileAttachment except this is specifically for images.
    Although this makes our lookups more complex it is nice in that the
    ImageFile field gives us some options specific to dealing with images.
    """
    topic = models.ForeignKey(Topic, verbose_name = _('topic'),
                              db_index = True, editable = False,
                              help_text = _('The topic this image belongs to.'),
                              related_name = 'image_attachments')
    height = models.IntegerField(_('image height'), editable = False,
                                 default = 0)
    width = models.IntegerField(_('image width'), editable = False,
                                default = 0)
    created = models.DateTimeField(_('created'), auto_now_add = True,
                                   editable = False,
                                   help_text = _('The time at which '
                                                 'this image was '
                                                 'originally uploaded.'))
    image = models.ImageField(_('image'), max_length = 256, db_index = True,
                              storage = fs,
                              upload_to = image_dir)
    owner = models.ForeignKey(User, verbose_name = _('owner'), editable = False,
                               help_text = _('The user that uploaded this '
                                             'image.'))

    ##################################################################
    #
    def __unicode__(self):
        return "<Image %s on topic '%s'>" % (self.image,
                                            self.topic.name)

    ##################################################################
    #
    def basename(self):
        return os.path.basename(self.image.name)

    ##################################################################
    #
    @permalink
    def get_absolute_url(self):
        return ('aswiki_topic_attachment', (self.topic.name, self.basename()))

####################################################################
#
class TopicVersion(models.Model):
    """
    As topics are modified in the wiki we need to keep track of the
    previous versions of their names and content. The TopicVersion
    model does this for us.

    We keep track of the name changes as well so we know what name a
    topic had in the past.

    The important thing about TopicVersions is that they are ordered
    by date. So to find all the changes going back in time you sort by
    the 'created' field on the TopicVersions related to a topic in
    descending order.
    """

    # Every TopicVersion is tied to the topic which it came from.
    #
    topic = models.ForeignKey(Topic, verbose_name = _('topic'), help_text =
                              _('The topic which this is a prior version of.'),
                              related_name = 'versions')
    name = models.CharField(_('name'), max_length = 128, db_index = True)
    author = models.ForeignKey(User, verbose_name = _('author'),
                               help_text = _('The author of this version '
                                             'of this topic.'))
    content_raw = models.TextField(_('content raw'), blank = True)
    created = models.DateTimeField(_('created'), db_index = True,
                                   help_text = _('The time at which '
                                                 'this version was '
                                                 'created. NOTE: This is not '
                                                 'the time this instance was '
                                                 'created but the `modified` '
                                                 'time of the Topic when this '
                                                 'version was created.'))
    reason = models.CharField(_('reason'), blank = True, max_length = 256,
                              help_text = _('A short blurb giving the reason '
                                            'for updating a topic. It can be '
                                            'blank'))
    normalized_created = models.CharField(_('normalized created'),
                                          db_index = True,
                                          max_length = 23, help_text =
                                          _('We store the normalized timestamp '
                                            'of the created field for more '
                                            'efficient lookups.'))

    class Meta:
        ordering = ("-created",)

    ####################################################################
    #
    def __unicode__(self):
        return u"Version from %s of Topic %s" % (self.normalized_created,
                                                 self.topic.name)

    ####################################################################
    #
    @permalink
    def get_absolute_url(self):
        """
        The absolute URL for a previous version of a topic is the timestamp
        the version was created as part of the actual topic's URL.

        This way it will always be obvious from the URL of a
        TopicVesion which Topic it belongs to (modulo the confusion of
        topics that have had their name changed.)

        We require that the timestamp be in a normalized form. It will
        always be in GMT. Our finest resolution is seconds.

        The normalized form will be: YYYY-MM-DD_HH:MM:SS

        XXX I hope saying that you will not get two updates of the same topic
            in the same second will happen. If it does we will just have to go
            to hundredths of a second as well.
        """
        return ("aswiki_topic_version", [self.topic.name,
                                         self.normalized_created])

###########################
###########################
#
# After this point we define some functions that are invoked when
# Topic specific signals are generated.
#

###########################################################################
#
def catch_topic_created(sender, **kwargs):
    """
    This function is invoked when the 'topic_created' signal is sent.

    We do the needful for new topics.. that is things that need to be done
    after a topic is created, but they can be done AFTER we have done
    everything we need to return from a django view function. This function
    could be moved in to some system that processes queued messages so as not
    to be called as part of the http request/response cycle.

    Arguments:
    - `sender`: The Topic that has been created
    - `**kwargs`: Not used, but required to be specified for signals.
    """

    # What do we need to do after a topic is created?  If a nascent topic
    # exists with the same name we must go through all of the topics that
    # referred to that nascent topic and regenerate their content and
    # references and then delete that nascent topic.
    #
    try:
        nascent = NascentTopic.objects.get(name__iexact = sender.name.lower())
        for topic in nascent.topic_set.all():
            # Saving a topic re-renders it.
            #
            topic.save()
        nascent.delete()
    except NascentTopic.DoesNotExist:
        pass

    return

###########################################################################
#
def catch_topic_renamed(sender, old_name, **kwargs):
    """
    Catch the signal for when a topic is renamed. We are given the
    topic as the sender. We need to go through all of the topics that
    reference this topic and re-write their raw contents so that any
    wikilinks in the raw content will point to the new topic name.

    We then call the 'catch_topic_created' function. Renaming a topic
    has the same effect as creating a new topic in that it may be
    replacing a NascentTopic, in which case any Topic that refers to
    that NascentTopic needs to refer to this newly renamed Topic.

    Arguments:
    - `sender`: The Topic that has been renamed
    - `old_name`: the name that this topic previously had.
    - `**kwargs`: the rest of the kwargs that are passed to a signal handler.
    """

    # Go through all of the topics that reference this topic and change the
    # old name wikilink in their raw content to the new name.
    #
    for topic in sender.referenced_by.all():
        topic.rename_referenced_topic(old_name, sender.name)

    # And then do what we do when we create a new topic..
    #
    catch_topic_created(sender, **kwargs)
    return

###########################################################################
#
def catch_topic_deleted(sender, **kwargs):
    """
    We need to find all Topics that referenced this topic and
    re-render them. This is because the link to this object should not
    show up as existing. This will also create the appropriate nascent
    topic reprsenting the deleted topic if necessary.

    Arguments:
    - `sender`:
    - `**kwargs`:
    """
#     n = NascentTopic.objects.get_or_create(lc_name = sender.name.lower(),
#                                            defaults={'author' : sender.author,
#                                                      'name'   : sender.name})

    # Go through all the topics that reference this topic and re-render
    # them, that will break the 'references' linkage and re-render the HTML
    # so that they show the links to this erstwhile topic as not-existing.
    #
    for topic in sender.referenced_by.all():
        topic.save()
    return

####################################################################
#
def catch_topic_notify(sender, *args, **kwargs):
    """
    Catches the 'topic_notify' signal which is sent when a topic has
    changed, and the user that did the change did not indicate it was
    a 'trivial' change.

    Mostly this is just to hook in to the `notification` app if it is
    available notifying users that are observing this topic that it
    has changed.

    Arguments:
    - `sender`: The topic that has been modified
    - `*args`: ignored here..
    - `**kwargs`: ignored here..
    """

    # If the `notification` app is available then send observation notices
    # for this topic.
    #
    if notification:
        notification.models.send_observation_notices_for(sender, 'topic_notify')
    return

###########################
###########################
#
# and here we register our listener functions with the appropriate signals
#
topic_created.connect(catch_topic_created)
topic_renamed.connect(catch_topic_renamed)
topic_deleted.connect(catch_topic_deleted)
topic_notify.connect(catch_topic_notify)

###########################
###########################
#
# Run our doctests.
#
def run_tests():
    import doctest
    doctest.testmod()

if __name__ == "__main__":
    _test()
