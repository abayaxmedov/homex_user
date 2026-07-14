from django.db import migrations


def attach_orphan_messages(apps, schema_editor):
    """Attach dashboard-created admin messages to their participant's chat.

    The dashboard endpoint used to save admin replies with ``chat=NULL``, so
    the client/master apps (which read the thread through the ``chat`` FK)
    never saw them. Resolve the chat from the message's client/master FK,
    creating the chat when the participant never wrote first.
    """
    SupportChat = apps.get_model("support", "SupportChat")
    SupportMessage = apps.get_model("support", "SupportMessage")

    for message in SupportMessage.objects.filter(chat__isnull=True).iterator():
        if message.client_id:
            chat, _ = SupportChat.objects.get_or_create(
                client_id=message.client_id,
                defaults={"participant_role": "client"},
            )
        elif message.master_id:
            chat, _ = SupportChat.objects.get_or_create(
                master_id=message.master_id,
                defaults={"participant_role": "master"},
            )
        else:
            continue
        message.chat = chat
        message.save(update_fields=["chat"])


class Migration(migrations.Migration):

    dependencies = [
        ("support", "0002_supportmessage_admin_supportchat_supportmessage_chat_and_more"),
    ]

    operations = [
        migrations.RunPython(attach_orphan_messages, migrations.RunPython.noop),
    ]
