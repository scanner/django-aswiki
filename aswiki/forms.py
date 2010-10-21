#
# File: $Id: forms.py 1898 2008-11-04 08:19:18Z scanner $
#
"""
This module contains the forms used by the aswiki views.
"""

# Django imports
#
from django import forms
from django.utils.translation import ugettext_lazy as _

from aswiki.models import ImageAttachment, FileAttachment

####################################################################
#
class TopicForm(forms.Form):
    """
    To post an update to a topic pretty much just requires the new
    content for the topic.

    NOTE: This form is used for both creating and editing topics.
    """
    content = forms.CharField(label = _('Content'), required = True,
                              widget = \
                                  forms.Textarea(attrs = { 'cols': 95,
                                                       'rows': 30,
                                                       'class' : 'monospaced'}))
    reason = forms.CharField(label = _('Reason'), required = False,
                             widget = forms.TextInput(attrs = { 'size': '80'}),
                             max_length = 250)

####################################################################
#
class EditTopicForm(forms.Form):
    """
    To post an update to a topic pretty much just requires the new
    content for the topic.

    NOTE: This form is used for both creating and editing topics.
    """
    content = forms.CharField(label = _('Content'), required = True,
                              widget = \
                                  forms.Textarea(attrs = { 'cols': 95,
                                                       'rows': 30,
                                                       'class' : 'monospaced'}))
    reason = forms.CharField(label = _('Reason'), required = False,
                             widget = forms.TextInput(attrs = { 'size': '80'}),
                             max_length = 250)
    trivial = forms.BooleanField(label = _('Trivial change'), required = False,
                                 help_text = _("When checked this change will "
                                               "not cause a notice to be sent "
                                               "to the users watching this "
                                               "topic"))

####################################################################
#
class RenameTopicForm(forms.Form):
    """
    To rename a topic pretty much just requires the new name.
    """
    new_name = forms.CharField(label = _('New Name'), max_length = 128,
                               required = True)
    reason = forms.CharField(label = _('Reason'), required = False,
                             widget = forms.TextInput(attrs = { 'size': '80'}),
                             max_length = 250)

####################################################################
#
class DeleteTopicForm(forms.Form):
    """
    To delete an object you need to submit a form via POST that validates.
    """
    reason = forms.CharField(label = _('Reason'), required = False,
                             widget = forms.TextInput(attrs = { 'size': '80'}),
                             max_length = 250)

####################################################################
#
class AttachmentUploadForm(forms.ModelForm):
    class Meta:
        model = FileAttachment

####################################################################
#
class ImageUploadForm(forms.ModelForm):
    class Meta:
        model = ImageAttachment

####################################################################
#
class RevertTopicForm(forms.Form):
    """
    To revert a topic you need to submit a form via POST that validates.
    """
    reason = forms.CharField(label = _('Reason'), required = False,
                             widget = forms.TextInput(attrs = { 'size': '80'}),
                             max_length = 250)
    trivial = forms.BooleanField(label = _('Trivial change'), required = False,
                                 help_text = _("When checked this change will "
                                               "not cause a notice to be sent "
                                               "to the users watching this "
                                               "topic"))

####################################################################
#
def add_override_field(form):
    """
    When a topic is write locked we require that some forms submitted
    for altering that topic have an additional field 'override.'
    Override must be set in order for us to allow an action to proceed
    on a topic that is write locked (and that we do own the write lock
    on.)

    This will augment the given form with the boolean required
    override field.

    Arguments:
    - `form`: The instance of the form class we are going to add the
              `override` field to.
    """
    form.fields['override'] = \
        forms.BooleanField(label = _("Override write lock"),
                           help_text = _("This topic is locked for "
                                         "editing by another user. You "
                                         "must select this if you want "
                                         "to override their lock and "
                                         "commit your changes anyways."))
    return

