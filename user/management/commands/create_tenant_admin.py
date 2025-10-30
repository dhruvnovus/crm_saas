from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from user.models import Tenant


class Command(BaseCommand):
    help = 'Create a tenant admin user (is_tenant_admin=True) linked to a tenant.'

    def add_arguments(self, parser):
        parser.add_argument('--username', required=True, help='Username (supports {tenant} placeholder when using --all)')
        parser.add_argument('--email', required=True, help='Email (supports {tenant} placeholder when using --all)')
        parser.add_argument('--password', required=True, help='Password')
        parser.add_argument('--tenant', help='Tenant name to associate with this user')
        parser.add_argument('--all', action='store_true', help='Create an admin user for ALL tenants. Uses {tenant} placeholder in username/email if provided.')

    def handle(self, *args, **options):
        User = get_user_model()
        username_tpl = options['username']
        email_tpl = options['email']
        password = options['password']

        if options['all']:
            tenants = Tenant.objects.all()
            if tenants.count() == 0:
                raise CommandError('No tenants found')
            for tenant in tenants:
                username = username_tpl.format(tenant=tenant.name.lower())
                email = email_tpl.format(tenant=tenant.name.lower())
                user = self._ensure_admin(User, tenant, username, email, password)
                # If this user is a Django superuser, ensure it remains global (no tenant binding)
                if getattr(user, 'is_superuser', False):
                    user.tenant = None
                    user.save(update_fields=['tenant'])
                self.stdout.write(self.style.SUCCESS(f'Admin ensured for tenant {tenant.name}: {user.username}'))
            return

        tenant_name = options.get('tenant')
        if not tenant_name:
            raise CommandError('Please provide --tenant or use --all')
        try:
            tenant = Tenant.objects.get(name=tenant_name)
        except Tenant.DoesNotExist:
            raise CommandError(f'Tenant "{tenant_name}" does not exist')

        user = self._ensure_admin(User, tenant, username_tpl, email_tpl, password)
        self.stdout.write(self.style.SUCCESS(f'Tenant admin created/updated: {user.username} (tenant: {tenant.name})'))

    def _ensure_admin(self, User, tenant, username, email, password):
        if User.objects.filter(username=username).exists():
            user = User.objects.get(username=username)
            user.email = email
            # Keep superusers global (no tenant binding). Otherwise, bind to tenant.
            if not getattr(user, 'is_superuser', False):
                user.tenant = tenant
            user.is_tenant_admin = True
            user.set_password(password)
            user.save()
            return user
        return User.objects.create_user(
            username=username,
            email=email,
            password=password,
            tenant=None if getattr(User, 'is_superuser', False) else tenant,
            is_tenant_admin=True,
        )


