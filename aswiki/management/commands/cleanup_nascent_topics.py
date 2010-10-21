"""
A management command which deletes nascent topics that should not exist
(ie: we have topics that exist with the same name as a nascent topic.)

Basicall loops through the NascentTopics, seeing if a Topic exists with
that name, and if it does, it deletes it.

Also, if a NascentTopic exists that has no Topic's that refer to it,
we delete it also. It is only Nascent if some topic refers to it.
"""

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
    help = "Delete NascentTopics that should not exist because there is "
    "actually a command with the same name or because no topic refers to them."

    def handle_noargs(self, **options):
        for nt in NascentTopic.objects.all():
            if Topic.objects.filter(name__iexact = nt.lc_name).count() > 0:
                # Lo, a topic exists with this name, delete this nascent
                # topic.
                #
                print "Topic exists -- Deleting NascentTopic '%s'" % nt.name
                nt.delete()
            elif nt.topic_set.all().count() == 0:
                # Hey, a nascent topic that no topic refers to.. these
                # should not exist either..
                #
                print "No referer -- Deleting NascentTopic '%s'" % nt.name
                nt.delete()


