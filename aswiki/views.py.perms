#
# File: $Id: views.py 1901 2008-11-04 09:18:52Z scanner $
#
"""
The views for our aswiki.

There are three primary views: the topic index, a specific topic, a
version of a specific topic.
"""

# Python standard lib imports
#
import datetime
import mimetypes
import os.path
from urllib import quote, unquote

# Django imports
#
from django.http import HttpResponseRedirect, HttpResponseForbidden, Http404
from django.views.generic.list_detail import object_list
from django.shortcuts import get_object_or_404, get_list_or_404
from django.core.urlresolvers import reverse
from django.utils.translation import ugettext_lazy as _
from django.utils.translation import ugettext as _u
from django.db.models import Q
from django import forms

# 3rd party module imports
#
# http://trac.apricot.com/projects/django-asutils
from asutils.utils import asrender_to_response, msg_user
from asutils.sendfile import send_file

# Try to import the django-notification app. We will use this for topic
# change notifications if it is installed.
#
try:
    import notification
except ImportError:
    notification = None

# When viewing versions of topics we want to present the diffs between any
# two versions if we can. Try to import the google diff_match_patch class.
#
try:
    from diff_match_patch import diff_match_patch
except:
    diff_match_patch = None


# Form imports
#
from aswiki.forms import TopicForm, RenameTopicForm, DeleteTopicForm
from aswiki.forms import AttachmentUploadForm, ImageUploadForm, EditTopicForm
from aswiki.forms import add_override_field, RevertTopicForm

# Model imports
#
from aswiki.models import Topic, TopicVersion, NORM_TIMESTAMP, TopicExists
from aswiki.models import FileAttachment, ImageAttachment

####################################################################
#
def topic_list(request, queryset, extra_context = None,
               template_name = 'aswiki/topic_list.html', **kwargs):
    """
    List all of the topics that exist. Basically this is just a
    wrapper around the generic `object_list` view, however, we may
    filter the QuerySet we are given if a 'q' parameter is
    provided. This gives us a simple search mechanism.

    Arguments:
    - `request`: The django http request object.
    - `queryset`: The queryset of Topics to list.
    - `**kwargs`: Everything else that we just pass through to the object_list
                  function.
    """

    if 'goto' in request.GET:
        # If the user calls this with the parameter 'goto' it is intended
        # to be shortcut for going to that specific topic. This lets us
        # easily goto/create topics from forms. WHat we do is basically
        # redirect to the topic being 'gone to.'
        #
        return HttpResponseRedirect(reverse('aswiki_topic',
                                            args = [request.GET['goto']]))
    elif 'q' in request.GET:
        # If a 'q' parameter was supplied in the URL this means someone wants
        # to filter the topics looking for something.
        #
        # XXX There is a problem here in that this search will also look inside
        #     of Topics that may be restricted to the current user. So you can
        #     find topics that have certain phrases in them, although you still
        #     can not actually view the topic.
        #
        q = request.GET['q']
        queryset = queryset.filter(Q(content_raw__icontains = q) | \
                                       Q(reason__icontains = q) | \
                                       Q(name__icontains = q))

        # We also stick the query itself in to the context so that our template
        # can display it.
        #
        if extra_context is None:
            extra_context = { 'query' : q}
        else:
            extra_context['query'] = q

    return object_list(request, queryset, extra_context = extra_context,
                       template_name = template_name, **kwargs)

###########################################################################
#
def topic(request, topic_name, template_name = 'aswiki/topic.html',
          extra_context = None, form_class = TopicForm,
          create_template = 'aswiki/topic_create.html'):
    """
    Display the most current version of a topic.

    If the given topic does not exist provide a link to the 'edit'
    page that will let the user create the topic.

    Arguments:
    - `request`: Django request object.
    - `topic_name`: The name of the topic to display. The name is url encoded.
    - `template_name`: Path to the template to use.
    - `extra_context`: Dictionary of extra context data to pass to the template.
    - `form_class`: If the user is creating a topic then this is the form we
                    use to valid their input.
    - `create_template`: The template to use if we are creating a topic that
                         does not exist yet.
    """
    # See if the topic exists. If it does not we let the user create it.
    #
    # NOTE: topic names are case preserving but case insensitive.
    #
    try:
        topic = Topic.objects.get(name__iexact = topic_name)

        # If the user does not have permission to see this topic
        # then we return a permission denied.
        #
        if not topic.permitted(request.user):
            return HttpResponseForbidden(_u("Sorry. You do not have sufficient"
                                            " permissions to view this topic."))

        info_dict = { 'topic' : topic }

        # XXX This is where we would do a permission check to make
        #     sure that the user has 'read' permission for this topic.
        #

    except Topic.DoesNotExist:
        # The topic does not exist. If this is a POST then we expect
        # a TopicForm from the user to create the topic.
        #
        preview = None
        if request.method == 'POST':

            # If the user hit 'cancel' then redirect them back to the topic
            # list.
            #
            if 'submit' not in request.POST:
                submit = 'create'
            else:
                submit = request.POST['submit'].lower()

            if submit == "cancel":
                return HttpResponseRedirect(reverse('aswiki_topic_index'))

            form = form_class(request.POST)
            if form.is_valid():
                if 'reason' in form.cleaned_data:
                    reason = form.cleaned_data['reason']
                else:
                    reason = None

                # If the user pressed 'preview' then we do not actually create
                # the topic. Instead we render a preview of the topic contents
                # and send it back with the filled out form to the user.
                #
                if submit == 'preview':
                    preview = form.cleaned_data['content']
                else:
                    topic = Topic(name = topic_name, reason = reason,
                                  author = request.user,
                                  content_raw = form.cleaned_data['content'])
                    topic.save()
                    msg_user(request.user,_("Topic '%s' created") % topic_name)
                    return HttpResponseRedirect(topic.get_absolute_url())
        else:
            form = form_class()

        # otherwise this is a GET or the POST failed, we need to render the
        # 'create topic' template.
        #
        info_dict = { 'topic_name' : topic_name,
                      'preview'    : preview,
                      'form'       : form }
        template_name = create_template

    # Otherwise! The topic exists. Display the topic.
    #
    return asrender_to_response(request, template_name, info_dict,
                                extra_context)

####################################################################
#
def topic_attachment(request, topic_name, attachment_name,
                     extra_context = None, **kwargs):
    """
    
    Arguments:
    - `request`: Django request object.
    - `topic_name`: The name of the topic to display.
    - `attachment_name`: The name of the attachment being fetched.
    - `extra_context`: Dictionary of extra context data to pass to the template.
    - `**kwargs`:
    """
    # If the user does not have permission to see this topic
    # then we return a permission denied.
    #
    topic = get_object_or_404(Topic, lc_name = topic_name.lower())
    if not topic.permitted(request.user):
        return HttpResponseForbidden(_u("Sorry. You do not have sufficient "
                                       "permissions to view this topic."))

    # Generic attachments and images are referenced under the same URL
    # directory, but are stored in different locations. See if the
    # attachment if an image attachment, and if it can not be found
    # there, see if it is a file attachment. The 'image' stored in the DB
    # is the full relative path name. We only care about the last segment
    # because only one such file can exist per upload directory.
    #
    attachment_name = "/" + attachment_name
    image = topic.image_attachments.filter(image__endswith = attachment_name)
    if image.count() != 0:
        # It is an image. Send the image content back to the caller
        # with the mimetype guessed by python.
        #
        image = image[0]
        mimetype, encoding = mimetypes.guess_type(image.image.path)
        if mimetype is None:
            # Huh? Not a known mimetype? going to call it an
            # application/octet-stream.
            #
            mimetype = 'application/octet-stream'
        return send_file(request, image.image.path, content_type = mimetype,
                         blksize = 65536)

    # See if this is a file attachment. If so we send it up, as an
    # application/octet-stream.
    #
    att = topic.file_attachments.filter(attachment__endswith = attachment_name)
    if att.count() == 0:
        # No such attachment. Return a 404.
        #
        raise Http404(_("No such attachment '%s'") % attachment_name)
    return send_file(request, att[0].attachment.path,
                     content_type = 'application/octet-stream', blksize = 65536)

####################################################################
#
def topic_upload_file(request, topic_name, extra_context = None,
                      form_class = AttachmentUploadForm,
                      template_name='aswiki/topic_upload_file.html',
                      **kwargs):
    """
    For uploading an attachment for this topic. This will upload and store
    the attachment in our upload directory. It will create an 'attachment'
    that will be associated with this topic.

    XXX This and _upload_image need to be refactored because they share
        some common code. There should probably only be one of these
        views.

    Arguments:
    - `request`: Django request object.
    - `topic_name`: The name of the topic to we uploading a file to.
    - `template_name`: Path to the template to use.
    - `extra_context`: Dictionary of extra context data to pass to the template.
    - `form_class`: The file upload form to use. It must at least a file
                    upload field named `attachment.'
    """
    topic = get_object_or_404(Topic, lc_name = topic_name.lower())

    # If the user does not have permission to see this topic
    # then we return a permission denied.
    #
    if not topic.permitted(request.user):
        return HttpResponseForbidden(_u("Sorry. You do not have sufficient "
                                       "permissions to view this topic."))

    # Since we need to know the file name before we instantiate the form
    # we will only accept things that are a POST _and_ that contain our
    # image.
    #
    if request.method == 'POST' and 'attachment' in request.FILES:

        # Now this is a little bit of magic. Basically we need to duplicate
        # the 'get_or_create()' functionality. However, since the location
        # of the actual files depends on the name of the topic we have to
        # pass to the form an instance of the FIleAttachment() object.. even
        # if it is ephemeral. This way the 'upload_to' callable defined for the
        # model will be able to determine the path name for the file (because
        # the path name depends on the topic name.)
        #
        # XXX Hopefully there are no problems with topic names having strange
        #     characters in them
        #
        file_name = request.FILES['attachment'].name
        try:
            attch = FileAttachment.objects.get(topic = topic,
                                               attachment = file_name)
            form = form_class(request.POST, request.FILES, instance = attch)
        except FileAttachment.DoesNotExist:
            attch = FileAttachment(topic = topic,
                                   attachment = file_name)
            form = form_class(request.POST, request.FILES, instance = attch)

        # At this point we have a form object that has all the root goop
        # in it to valid and save if it validates. The 'save' operation
        # will do the work of moving the uploaded file in to its final
        # resting place.
        #
        if form.is_valid():
            attch = form.save(commit = False)
            attch.owner = request.user
            attch.save()
            # We save the topic also, in order to re-render the content in case
            # there was an <<attachlist>> directive in the topic.
            #
            topic.save(notify = False)
            msg_user(request.user,_('File "%s" successfully uploaded.') % \
                         os.path.basename(attch.attachment.name))
            return HttpResponseRedirect(topic.get_absolute_url())
    else:
        form = form_class()
    return asrender_to_response(request, template_name, { 'form'  : form,
                                                          'topic' : topic},
                                extra_context, **kwargs)

####################################################################
#
def topic_delete_file(request, topic_name, file_name, extra_context = None,
                      template_name = 'aswiki/topic_delete_file.html',
                      **kwargs):
    """
    When invoked with a get returns the template. The topic, and a
    FileAttachment corresponding to that file name must exist. When invoked
    with a post deletes the specified file, and associated FileAttachment
    object, and redirect back to the topic's view.

    Arguments:
    - `request`: Django request object.
    - `topic_name`: The name of the topic to display.
    - `template_name`: Path to the template to use.
    - `extra_context`: Dictionary of extra context data to pass to the template.
    - `**kwargs`: Extra arguments passed through the template renderer.
    """
    topic = get_object_or_404(Topic, lc_name = topic_name.lower())

    # If the user does not have permission to see this topic
    # then we return a permission denied.
    #
    if not topic.permitted(request.user):
        return HttpResponseForbidden(_u("Sorry. You do not have sufficient "
                                       "permissions to view this topic."))
    raise NotImplemented

####################################################################
#
def topic_upload_image(request, topic_name, extra_context = None,
                            form_class = ImageUploadForm,
                            template_name='aswiki/topic_upload_image.html',
                            **kwargs):
    """
    For uploading an image for this topic. This will upload and store
    the attachment in our upload directory. It will create an 'image'
    that will be associated with this topic.

    XXX This and _upload_attachment need to be refactored because they share
        some common code. There should probably only be one of these
        views.
    
    Arguments:
    - `request`: Django request object.
    - `topic_name`: The name of the topic to display.
    - `template_name`: Path to the template to use.
    - `extra_context`: Dictionary of extra context data to pass to the template.
    - `form_class`: The file upload form to use. It must at least a file
                    upload field named `image.'
    """
    topic = get_object_or_404(Topic, lc_name = topic_name.lower())

    # If the user does not have permission to see this topic
    # then we return a permission denied.
    #
    if not topic.permitted(request.user):
        return HttpResponseForbidden(_u("Sorry. You do not have sufficient "
                                       "permissions to view this topic."))

    # Since we need to know the file name before we instantiate the form
    # we will only accept things that are a POST _and_ that contain our
    # image.
    #
    if request.method == 'POST' and 'image' in request.FILES:

        # Now this is a little bit of magic. Basically we need to duplicate
        # the 'get_or_create()' functionality. However, since the location
        # of the actual image depends on the name of the topic we have to
        # pass to the form an instance of the ImageAttachment() object.. even
        # if it is ephemeral. This way the 'upload_to' callable defined for the
        # model will be able to determine the path name for the file (because
        # the path name depends on the topic name.)
        #
        # XXX Hopefully there are no problems with topic names having strange
        #     characters in them
        #
        file_name = request.FILES['image'].name
        try:
            image = ImageAttachment.objects.get(topic = topic,
                                                image = file_name)
            form = form_class(request,POST, request.FILES, instance = image)
        except ImageAttachment.DoesNotExist:
            image = ImageAttachment(topic = topic,
                                    image = file_name)
            form = form_class(request.POST, request.FILES, instance = image)

        # At this point we have a form object that has all the root goop
        # in it to valid and save if it validates. The 'save' operation
        # will do the work of moving the uploaded file in to its final
        # resting place.
        #
        if form.is_valid():
            image = form.save(commit = False)
            image.owner = request.user
            image.save()
            msg_user(request.user, _('Image "%s" successfully uploaded.') \
                         % image.image.name)
            return HttpResponseRedirect(topic.get_absolute_url())
    else:
        form = form_class()
    return asrender_to_response(request, template_name, { 'form'  : form,
                                                          'topic' : topic},
                                extra_context, **kwargs)

###########################################################################
#
def topic_list_versions(request, topic_name, extra_context = None,
                        template_name = 'aswiki/topic_list_versions.html',
                        **kwargs):
    """
    Present a list/browser of the various versions of this topic,
    hopefully in a useful display.

    Arguments:
    - `request`: Django request object.
    - `topic_name`: The name of the topic to display.
    - `template_name`: Path to the template to use.
    - `extra_context`: Dictionary of extra context data to pass to the template.
    """
    topic = get_object_or_404(Topic, name__iexact = topic_name)

    # If the user does not have permission to see this topic
    # then we return a permission denied.
    #
    if not topic.permitted(request.user):
        return HttpResponseForbidden(_u("Sorry. You do not have sufficient "
                                       "permissions to view this topic."))

    # XXX We get versions here instead of in the template in case we later
    #     need to restrict the versions you can get due to permissions
    #     or something.
    versions = topic.versions.all()

    if extra_context is None:
        extra_context = {}
    extra_context['topic'] = topic

    return object_list(request, versions, template_name = template_name,
                       extra_context = extra_context, **kwargs)

###########################################################################
#
def topic_edit(request, topic_name, template_name = 'aswiki/topic_edit.html',
               extra_context = None, form_class = EditTopicForm):
    """
    Edit a topic. On GET returns the form for the topic. On POST
    creates a new TopicVersion based on the current topic's contents,
    and then updates the topic with the new content posted by the
    user.

    If we can not fetch the topic given its name that means this user
    is creating this topic, in that case we re-direct them to the
    topic() view which will allow them to create the topic.

    XXX edit & rename & delete are almost entirely identical. We should probably
        collapse these in to a single more generic view.

    Arguments:
    - `request`: Django request object.
    - `topic_name`: The name of the topic to display.
    - `template_name`: Path to the template to use.
    - `extra_context`: Dictionary of extra context data to pass to the template.
    - `form_class`: The form for editing this topic. It must have 'content'.
                    It may also have the optional field 'reason.'
    """
    topic = get_object_or_404(Topic, name__iexact = topic_name)

    if not topic.permitted(request.user):
        return HttpResponseForbidden(_u("Sorry. You do not have sufficient "
                                       "permissions to view this topic."))
    preview = None
    if request.method == 'POST':

        # If the user hit 'cancel' then redirect them back to the topic.
        # This also releases the write lock if this user is the owner
        # of the write lock.
        #
        if 'submit' not in request.POST:
            submit = 'submit'
        else:
            submit = request.POST['submit'].lower()
        if submit == "cancel":
            msg_user(request.user,_("Edit canceled. Topic '%s' not "
                                    "modified.") % topic_name)
            topic.release_write_lock(request.user)
            return HttpResponseRedirect(topic.get_absolute_url())

        # If this topic is write locked NOT by this user then we require
        # the 'force' boolean field in our form.
        #
        form = form_class(request.POST)
        if topic.get_write_lock(request.user) is False:
            add_override_field(form)

        if form.is_valid():
            if 'reason' in form.cleaned_data:
                reason = form.cleaned_data['reason']
            else:
                reason = _("Topic edited by %s") % request.user.username

            # If the user pressed 'preview' then we do not actually update
            # the topic. Instead we render a preview of the topic contents
            # and send it back with the filled out form to the user.
            #
            if submit == 'preview':
                preview = form.cleaned_data['content']
            else:
                topic.update_content(request.user, form.cleaned_data['content'],
                                     reason = reason,
                                     trivial = form.cleaned_data['trivial'])
                msg_user(request.user,_("Topic '%s' edited") % topic_name)

                # If we got to this point then we can release the write lock.
                # We can force this release because no matter what the write
                # lock is to be released - the user HAD to check the 'override'
                # field on the form for the form to pass the 'is_valid()' check
                # since the 'override' field is a required boolean field.
                #
                topic.release_write_lock(request.user, force = True)
                return HttpResponseRedirect(topic.get_absolute_url())
    else:
        form = form_class({ 'content' : topic.content_raw })

        # If this topic is write locked NOT by this user then we require
        # the 'force' boolean field in our form.
        #
        if topic.get_write_lock(request.user) is False:
            add_override_field(form)

    return asrender_to_response(request, template_name, { 'topic'   : topic,
                                                          'form'    : form,
                                                          'preview' : preview},
                                extra_context)

###########################################################################
#
def topic_rename(request, topic_name,
                 template_name = 'aswiki/topic_rename.html',
                 extra_context = None, form_class = RenameTopicForm):
    """
    To change a topic's name is actually a pretty serious
    operation. All topics that refer to this topic have to have their
    content updated. Also since it is a significant operation we
    separate it out from just editing a topic's contents, hence it is
    in its own view.

    XXX edit & rename & delete are almost entirely identical. We should probably
        collapse these in to a single more generic view.

    Arguments:
    - `request`: Django request object.
    - `topic_name`: The name of the topic to display.
    - `template_name`: Path to the template to use.
    - `extra_context`: Dictionary of extra context data to pass to the template.
    - `form_class`: The form for renaming this topic. It must have 'name'.
                    It may also have the optional field 'reason.'
    """
    topic = get_object_or_404(Topic, name__iexact = topic_name)

    if not topic.permitted(request.user):
        return HttpResponseForbidden(_u("Sorry. You do not have sufficient "
                                        "permissions to view this topic."))

    if request.method == 'POST':
        # If the user hit 'cancel' then redirect them back to the topic.
        # This also releases the write lock if this user is the owner
        # of the write lock.
        #
        if 'submit' not in request.POST:
            submit = 'rename'
        else:
            submit = request.POST['submit'].lower()
        if submit == "cancel":
            topic.release_write_lock(request.user)
            msg_user(request.user,_("Rename canceled. Topic '%s' not "
                                    "renamed.") % topic_name)
            return HttpResponseRedirect(topic.get_absolute_url())

        # If this topic is write locked NOT by this user then we require
        # the 'force' boolean field in our form.
        #
        form = form_class(request.POST)
        if topic.get_write_lock(request.user) is False:
            add_override_field(form)

        if form.is_valid():
            new_name = form.cleaned_data['new_name']
            if 'reason' in form.cleaned_data:
                reason = form.cleaned_data['reason']
            else:
                reason = _("Topic renamed from '%s' to '%s'") % \
                         (topic_name, new_name)

            # This call will create a new TopicVersion, update this topic's
            # name, save the topic and either update all the topics that
            # refer to this topic by name, or set in motion the process to
            # do that.
            #
            # However, watch out for the exception when they are trying to
            # rename a topic to the same name as one that already exists.
            #
            #
            try:
                topic.rename(request.user, new_name, reason = reason)
                msg_user(request.user, _("Topic renamed from '%s' "
                                         "to '%s'") % (topic_name, new_name))
            except TopicExists:
                msg_user(request.user, _("You can not rename this topic "
                                         "to '%s', becaues a topic with that "
                                         "name already exists.") % new_name)
            # If we got to this point then we can release the write lock.
            # We can force this release because no matter what the write
            # lock is to be released - the user HAD to check the 'override'
            # field on the form for the form to pass the 'is_valid()' check
            # since the 'override' field is a required boolean field.
            #
            topic.release_write_lock(request.user, force = True)
            return HttpResponseRedirect(topic.get_absolute_url())
    else:
        form = form_class({ 'new_name' : topic.name })
        # If this topic is write locked NOT by this user then we require
        # the 'force' boolean field in our form.
        #
        if topic.get_write_lock(request.user) is False:
            add_override_field(form)

    return asrender_to_response(request, template_name, { 'topic' : topic,
                                                          'form'  : form},
                                extra_context)

###########################################################################
#
def topic_delete(request, topic_name, form_class = DeleteTopicForm,
                 template_name = 'aswiki/topic_delete.html',
                 extra_context = None):
    """
    Delete a topic. On GET returns the form for the topic. on POST if
    the form has the field 'delete' set to be True, then it will
    delete the topic and redirect you back to the topic list.

    XXX We should support an AJAX method on this call that lets a form
        be deleted via an AJAXy popup. Bringing up a page saying `do
        you wish to delete this form, check yes here` is a bit much.

    Arguments:
    - `request`: Django request object.
    - `topic_name`: The name of the topic to display.
    - `template_name`: Path to the template to use.
    - `extra_context`: Dictionary of extra context data to pass to the template.
    - `form_class`: The form to present to the user for deleting the topic.
                    It must have at least boolean field 'delete'.
    """
    topic = get_object_or_404(Topic, name__iexact = topic_name)

    # The user must be permitted AND must have the 'delete' permission.
    #
    if not topic.permitted(request.user):
        return HttpResponseForbidden(_u("Sorry. You do not have sufficient "
                                       "permissions to view this topic."))
    if not (request.user.has_perm('aswiki.delete_topic') or \
                getattr(request.user, 'has_row_perm', lambda x,y: False)(self, 'delete')):
        return HttpResponseForbidden(_u("Sorry. You do not have sufficient "
                                       "permissions to view this topic."))

    if request.method == 'POST':

        # If the user hit 'cancel' then redirect them back to the topic.
        # This also releases the write lock if this user is the owner
        # of the write lock.
        #
        if 'submit' in request.POST and \
                request.POST['submit'].lower() == 'cancel':
            msg_user(request.user,_("Delete canceled. Topic '%s' not "
                                    "deleted") % topic_name)
            topic.release_write_lock(request.user)
            return HttpResponseRedirect(topic.get_absolute_url())

        # If this topic is write locked NOT by this user then we require
        # the 'force' boolean field in our form.
        #
        form = form_class(request.POST)
        if topic.get_write_lock(request.user) is False:
            add_override_field(form)

        if form.is_valid():
            if 'reason' in form.cleaned_data:
                reason = form.cleaned_data['reason']
            else:
                reason = _("Topic deleted by %s") % request.user.username

            # If we got to this point then we can release the write lock.
            # We can force this release because no matter what the write
            # lock is to be released - the user HAD to check the 'override'
            # field on the form for the form to pass the 'is_valid()' check
            # since the 'override' field is a required boolean field.
            #
            # NOTE: We have to do this before we actually mark the topic
            # as deleted.
            #
            topic.release_write_lock(request.user, force = True)

            # This call will create a new TopicVersion, and mark this topic
            # as deleted.
            #
            topic.mark_as_deleted(request.user, reason = reason)

            msg_user(request.user,_("Topic '%s' deleted") % topic_name)
            return HttpResponseRedirect(reverse('aswiki_topic_index'))
    else:
        form = form_class({ 'reason' : _("Topic deleted by %s") \
                                % request.user.username })
        # If this topic is write locked NOT by this user then we require
        # the 'force' boolean field in our form.
        #
        if topic.get_write_lock(request.user) is False:
            add_override_field(form)

    return asrender_to_response(request, template_name, { 'topic' : topic,
                                                          'form'  : form},
                                extra_context)

###########################################################################
#
def topic_set_property(request, topic_name):
    """
    This view controls setting two properties on topics: lock &
    restricted. Unlike edit, rename, or delete it does not have a template.
    This view will redirect the user back to the topic. This is a separate
    view from 'edit' because it requires a permissions check to see if the
    user has the permission to lock/unlock a topic, or restrict/unrestrict a
    topic.

    XXX We will need to visit how this sort of view works in the future with
        respect to things like JSON.

    XXX Yes. I know this does database modifications on GET. Should make the
        template post a form.

    NOTE: We expect to be called with a single parameter called "op" and
          this will be one of: lock, unlock, restrict, unrestrict.

    For lock/unlock the user must have the 'lock_topic' permission.
    For restrict/unrestrict the user must have the 'restrict' permission.
    """
    topic = get_object_or_404(Topic, name__iexact = topic_name)

    if not topic.permitted(request.user):
        return HttpResponseForbidden(_u("Sorry. You do not have sufficient "
                                       "permissions to view this topic."))

    # The only parameter we accept and the one we expect is 'op'.
    #
    # XXX No form involved in this yet so we just handle this manually for
    #     now.
    #
    if "op" not in request.REQUEST:
        return HttpResponseBadRequest("Required parameter 'op' is missing.")

    # Now do the operation request.. fail if not a valid operation.
    #
    op = str(request.REQUEST['op'].lower())
    if op in ('unlock', 'lock'):
        if not request.user.has_perm('aswiki.lock_topic'):
            return HttpResponseForbidden(_u("Sorry. You do not have sufficient "
                                           "permissions to view this topic."))
        if op == 'lock':
            topic.locked = True
            # XXX Should not use 'msg_user' if doing json..
            #
            msg_user(request.user,_("Topic '%s' is now locked") % topic.name)
        else:
            topic.locked = False
            # XXX Should not use 'msg_user' if doing json..
            #
            msg_user(request.user,_("Topic '%s' is now unlocked") % topic.name)
    elif op in ('restrict', 'unrestrict'):
        if not request.user.has_perm('aswiki.restricted'):
            return HttpResponseForbidden(_u("Sorry. You do not have sufficient "
                                           "permissions to view this topic."))
        if op == 'restrict':
            topic.restricted = True
            # XXX Should not use 'msg_user' if doing json..
            #
            msg_user(request.user,
                     _("Topic '%s' is now restricted") % topic.name)
        else:
            topic.restricted = False
            # XXX Should not use 'msg_user' if doing json..
            #
            msg_user(request.user,
                     _("Topic '%s' is now unrestricted") % topic.name)
    elif op in ('observe', 'stop_observing'):
        # You can only observe or stop observing if the `notification` app
        # is installed.
        #
        if notification:
            if op == 'observe':
                notification.models.observe(topic, request.user,
                                            "aswiki_topic_change",
                                            signal = 'topic_notify')
                msg_user(request.user,
                         _("You are now watching the topic '%s'") % topic.name)
            else:
                notification.models.stop_observing(topic, request.user,
                                                   signal = 'topic_notify')
                msg_user(request.user,
                         _("You are no longer watching the topic '%s'") % \
                             topic.name)
        # We do not fall through to the end as there is no reason to save
        # the topic when it is being observed or not. The saving happens
        # in the notification app.
        #
        return HttpResponseRedirect(topic.get_absolute_url())
    else:
        return HttpResponseBadRequest("'%s' is not a valid 'op' value." % op)

    # XXX If this came in via JSON we should return a nice 200 response, not a
    #     redirect.
    #
    topic.save()
    return HttpResponseRedirect(topic.get_absolute_url())


###########################################################################
#
def topic_revert(request, topic_name, created,
                 template_name = 'aswiki/topic_revert.html',
                 form_class = RevertTopicForm,
                 extra_context = None):
    """
    If called with a GET presents the form, asking the user if they wish
    to revert the topic to this version.

    If called with a POST, reverts the topic to this version.
    
    Arguments:
    - `request`: Django request object.
    - `topic_name`: The name of the topic to display.
    - `created`: A string in the format 'YYYY-MM-DD_HH:MM:SS'
    - `template_name`: Path to the template to use.
    - `form_class`: The form that must validate if this view is called via POST
                    before we revert this topic.
    - `extra_context`: Dictionary of extra context data to pass to the template.
    """
    topic = get_object_or_404(Topic, name__iexact = topic_name)

    if not topic.permitted(request.user):
        return HttpResponseForbidden(_u("Sorry. You do not have sufficient "
                                       "permissions to view this topic."))
    # Convert the 'created' field in a datetime object that we can use
    # to look up the appropriate topic version.
    #
    version = datetime.datetime.strptime(created, NORM_TIMESTAMP)

    # XXX a bit of a hack, because we truncate versions at seconds
    #     and it may likely be saved with a finer resolution then that
    #     we need to do bump up the version we got to 999999 usec
    #     so that he 'lte' matches properly. If we go to usec based
    #     versions we will just remove this code.
    #
    lte_version = version + datetime.timedelta(microseconds = 999999)

    # Get the first topic version earlier or equal to 'created' time. If
    # we find some version, but it is not an exact match, redirect to the
    # exact match. If we find no such version, raise a 404.
    #
    topic_version = get_list_or_404(TopicVersion, topic = topic,
                                    created__lte = lte_version)[0]

    # We need to truncase the 'created' attribute of the TopicVersion
    # we got back so that it has the same resolution as the 'created'
    # parameter passed in.
    #
    # XXX If we go to usec we should be able to get rid of this code too.
    #
    tv_created = datetime.datetime(topic_version.created.year,
                                   topic_version.created.month,
                                   topic_version.created.day,
                                   topic_version.created.hour,
                                   topic_version.created.minute,
                                   topic_version.created.second)
    if tv_created != version:
        raise Http404

    if request.method == 'POST':
        if 'submit' in request.POST and \
                request.POST['submit'].lower() == "cancel":
            msg_user(request.user,_("Revert canceled. Topic '%s' not "
                                    "modified.") % topic.name)
            topic.release_write_lock(request.user)
            return HttpResponseRedirect(topic.get_absolute_url())

        # If the topic is locked you must be staff to unlock it.
        # XXX Should probably look for a 'lock' permission
        #
        if topic.locked and not user.is_staff:
            raise HttpResponseForbidden(_u("Topic '%s' is locked.") % \
                                            topic.name)
        # If this topic is write locked NOT by this user then we require
        # the 'force' boolean field in our form.
        #
        form = form_class(request.POST)
        if topic.get_write_lock(request.user) is False:
            add_override_field(form)

        if form.is_valid():
            if 'reason' in form.cleaned_data and \
                    form.cleaned_data['reason'] is not None and \
                    form.cleaned_data['reason'] != "":
                reason = form.cleaned_data['reason']
            else:
                reason = _("Topic reverted to version %s by %s") % \
                    (topic_version.normalized_created, request.user.username)
            topic.update_content(request.user, topic_version.content_raw,
                                 reason = reason,
                                 trivial = form.cleaned_data['trivial'])
            msg_user(request.user,_("Topic '%s' reverted to version from %s") \
                         % (topic_name, topic_version.normalized_created))

            # If we got to this point then we can release the write lock.
            # We can force this release because no matter what the write
            # lock is to be released - the user HAD to check the 'override'
            # field on the form for the form to pass the 'is_valid()' check
            # since the 'override' field is a required boolean field.
            #
            topic.release_write_lock(request.user, force = True)
            return HttpResponseRedirect(topic.get_absolute_url())
    else:
        form = form_class()

        # If this topic is write locked NOT by this user then we require
        # the 'force' boolean field in our form.
        #
        if topic.get_write_lock(request.user) is False:
            add_override_field(form)

    return asrender_to_response(request, template_name,
                                { 'topic'   : topic,
                                  'topic_version' : topic_version,
                                  'form'    : form, },
                                extra_context)

###########################################################################
#
def topic_version(request, topic_name, created,
                  template_name = 'aswiki/topic_version.html',
                  extra_context = None):
    """
    Look up a previous version of a topic by the 'created' date.

    We are given the 'created' date in its normalized form so we can
    attempt to look it up directly by that key. However, if that
    lookup fails we will parse the created string in to a datetime and
    lookup the first topic version for the given topic older then that
    date. If we manage to find such a topic version, we will http
    redirect the user to the exact url of that topic version.

    Arguments:
    - `request`: Django request object.
    - `topic_name`: The name of the topic to display.
    - `created`: A string in the format 'YYYY-MM-DD_HH:MM:SS'
    - `template_name`: Path to the template to use.
    - `extra_context`: Dictionary of extra context data to pass to the template.
    """
    topic = get_object_or_404(Topic, name__iexact = topic_name)

    if not topic.permitted(request.user):
        return HttpResponseForbidden(_u("Sorry. You do not have sufficient "
                                       "permissions to view this topic."))

    # Convert the 'created' field in a datetime object that we can use
    # to look up the appropriate topic version.
    #
    version = datetime.datetime.strptime(created, NORM_TIMESTAMP)

    # XXX a bit of a hack, because we truncate versions at seconds
    #     and it may likely be saved with a finer resolution then that
    #     we need to do bump up the version we got to 999999 usec
    #     so that he 'lte' matches properly. If we go to usec based
    #     versions we will just remove this code.
    #
    lte_version = version + datetime.timedelta(microseconds = 999999)

    # Get the first topic version earlier or equal to 'created' time. If
    # we find some version, but it is not an exact match, redirect to the
    # exact match. If we find no such version, raise a 404.
    #
    topic_version = get_list_or_404(TopicVersion, topic = topic,
                                    created__lte = lte_version)[0]

    # We need to truncase the 'created' attribute of the TopicVersion
    # we got back so that it has the same resolution as the 'created'
    # parameter passed in.
    #
    # XXX If we go to usec we should be able to get rid of this code too.
    #
    tv_created = datetime.datetime(topic_version.created.year,
                                   topic_version.created.month,
                                   topic_version.created.day,
                                   topic_version.created.hour,
                                   topic_version.created.minute,
                                   topic_version.created.second)

    if tv_created != version:
        return HttpResponseRedirect(\
            reverse('aswiki_topic_version',
                    args = [topic_name, tv_created.strftime(NORM_TIMESTAMP)]))

    # otherwise they have found an exact version. By default we compare
    # this version with the current version of the topic.
    #
    # XXX maybe we should compare to the next later version? or maybe just
    #     have an argument that we can use to test which version to compare
    #     against.
    #
    # XXX Really it should compare against the previous version, some specified
    #     version (or the current topic) instead of the current topic always.
    #
    # If we have the diff-match-patch module imported use it to extract
    # diffs.
    #
    if diff_match_patch:
        dmp = diff_match_patch()
        diffs = dmp.diff_main(topic_version.content_raw, topic.content_raw)
        diffs_html = dmp.diff_prettyHtml(diffs)
    else:
        diffs_html = None

    return asrender_to_response(request, template_name,
                                { 'topic_version': topic_version,
                                  'diffs_html' : diffs_html,
                                  'topic' : topic },
                                extra_context)

