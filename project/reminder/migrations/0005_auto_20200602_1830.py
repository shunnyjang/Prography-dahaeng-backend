# Generated by Django 3.0.5 on 2020-06-02 09:30

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('record', '0002_post_image'),
        ('reminder', '0004_auto_20200601_1855'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='reminder',
            unique_together={('post', 'interval')},
        ),
    ]
