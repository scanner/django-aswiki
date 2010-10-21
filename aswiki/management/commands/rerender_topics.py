"""
A management command which goes through all of the topics and re-renders
their content_raw in to content_formatted.

This also causes all of the NascentTopics to be linked, and
potentially created as well as re-do the inter-linking of referenced
Topics as well.

Basically loops through the Topics, calling the 'save()' method of the
topic which will force it to re-render and update its relationship.

This is handy if we change/import the creoleparser. Also, for cleaning
up older ersions of aswiki where we need to revalidate all inter-topic
references and create any NascentTopics that should be made.
"""

import sys

# Django system imports
#
from django.core.management.base import NoArgsCommand
from django.core.management.base import CommandError

# Model imports
#
from aswiki.models import NascentTopic, Topic

##################################################################
##################################################################
#
class Command(NoArgsCommand):
    help = "Goes through all Topic's calling their 'save()' method which "
    "causes them to be re-rendered and updates their relations to other "
    "Topics and to NascentTopics."

    def handle_noargs(self, **options):
        for t in Topic.objects.all():
            sys.stdout.write('.')
            sys.stdout.flush()
            t.save()
        print ""
