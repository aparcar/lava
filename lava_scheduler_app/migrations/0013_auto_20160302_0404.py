# -*- coding: utf-8 -*-
# Generated by Django 1.9.2 on 2016-03-02 04:04
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lava_scheduler_app', '0012_auto_20160208_1600'),
    ]

    operations = [
        migrations.AlterField(
            model_name='devicetype',
            name='health_denominator',
            field=models.IntegerField(choices=[(0, b'hours'), (1, b'jobs')], default=0, help_text=b'Choose to submit a health check every N hours or every N jobs. Balance against the duration of a health check job and the average job duration.', verbose_name=b'Initiate health checks by hours or by jobs.'),
        ),
    ]
