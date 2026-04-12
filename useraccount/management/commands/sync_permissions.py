"""
useraccount/management/commands/sync_permissions.py

Run once after migrating:
    python manage.py sync_permissions

This inserts every permission defined in ALL_PERMISSIONS into the database.
Safe to run multiple times (uses get_or_create).
"""
from django.core.management.base import BaseCommand
from useraccount.models import Permission, ALL_PERMISSIONS


class Command(BaseCommand):
    help = 'Sync permission definitions into the Permission table'

    def handle(self, *args, **options):
        created_count = 0
        for codename, name, group in ALL_PERMISSIONS:
            _, created = Permission.objects.get_or_create(
                codename=codename,
                defaults={'name': name, 'group': group}
            )
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f'  Created: {codename}'))
            else:
                self.stdout.write(f'  Exists:  {codename}')

        self.stdout.write(self.style.SUCCESS(
            f'\nDone. {created_count} new permission(s) added, '
            f'{len(ALL_PERMISSIONS) - created_count} already existed.'
        ))
