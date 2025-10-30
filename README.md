# CRM SaaS - Multi-Tenant Django Application

A comprehensive Django-based CRM SaaS application featuring multi-tenant database architecture where each tenant gets their own isolated database. This application provides complete data isolation, secure authentication, and comprehensive API logging.

## 🚀 Features

- **Multi-Tenant Architecture**: Each tenant gets their own isolated database
- **Token-Based Authentication**: Secure API authentication with Django REST Framework
- **Dynamic Database Creation**: Automatically creates new databases for new tenants
- **MySQL Support**: Robust MySQL database management
- **Complete Data Isolation**: Full separation of tenant data
- **API Request Logging**: Comprehensive history tracking for all API calls
- **Interactive API Documentation**: Swagger UI and ReDoc integration
- **Tenant Management**: Full CRUD operations for tenant management
- **User Management**: Multi-level user management within tenants

## 🏗️ Architecture

### Database Architecture
- **Main Database**: `crm_saas_main` - Stores tenant information and user accounts
- **Tenant Databases**: `crm_tenant_{tenant_name}` - Isolated databases for each tenant
- **Database Routing**: Automatic routing based on tenant context

### Models
- **Tenant**: Stores tenant information and database details
- **CustomUser**: Extended user model with tenant relationship
- **TenantUser**: Junction model for users within tenant databases
- **History**: Comprehensive API request logging

## 📋 Prerequisites

- Python 3.8+
- MySQL 5.7+
- pip
- Git

## 🛠️ Installation & Setup

### 1. Clone the Repository
```bash
git clone <repository-url>
cd crm_saas
```

### 2. Create Virtual Environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Database Setup
```bash
# Create the main database
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS crm_saas_main;"
```

### 5. Configure Settings
Update database credentials in `crm_saas/settings.py` if needed:
```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'crm_saas_main',
        'USER': 'root',
        'PASSWORD': 'your_password',
        'HOST': '127.0.0.1',
        'PORT': '3306',
    }
}
```

### 6. Run Migrations
```bash
python manage.py makemigrations
python manage.py migrate
```

### 7. Create Superuser
```bash
python manage.py createsuperuser
```

### 8. Tenant Setup (per-tenant DB)
```bash
# Create initial migrations for local model changes (main DB)
python manage.py makemigrations
python manage.py migrate

# Create the token table for a tenant (if missing)
python manage.py create_token_table <TENANT_NAME>

# If a tenant DB needs structure setup/fix (tables, FKs, columns)
# All tenants
python manage.py setup_tenant_tables --all-tenants
# Or by tenant id
python manage.py setup_tenant_tables --tenant-id <TENANT_ID>
# Or by database name
python manage.py setup_tenant_tables --database-name crm_tenant_<tenant>
# Fix foreign keys/columns across all tenants
python manage.py setup_tenant_tables --fix-foreign-keys

# Run full migrations for a specific tenant (creates DB if needed)
python manage.py migrate_tenant <TENANT_NAME> --create

# Apply only leads app migrations to one or all tenants
python manage.py migrate_leads --tenant-name <TENANT_NAME>
python manage.py migrate_leads --all-tenants
# Optionally generate app migrations before applying to tenants
python manage.py migrate_leads --all-tenants --makemigrations

# Migrate auth token tables inside a tenant DB
python manage.py migrate_authtoken_to_tenant <TENANT_NAME>

# If authentication tables are missing/broken in one or all tenants
python manage.py fix_tenant_auth <TENANT_NAME>
python manage.py fix_tenant_auth <TENANT_NAME> --all
```

### 9. Start Development Server
```bash
python manage.py runserver
```

## 📚 API Documentation

### Interactive Documentation
- **Swagger UI**: `http://localhost:8000/swagger/` - Interactive API testing
- **ReDoc**: `http://localhost:8000/redoc/` - Alternative documentation view
- **OpenAPI Schema**: `http://localhost:8000/swagger.json` - Raw OpenAPI schema

### Admin Panel
- **Django Admin**: `http://localhost:8000/admin/` - Database administration

## 🔗 API Endpoints

### Authentication Endpoints
- `POST /api/auth/register/` - Register new user and create tenant
- `POST /api/auth/login/` - User login and token generation
- `POST /api/auth/logout/` - User logout and token deletion
- `GET /api/auth/profile/` - Get current user profile
- `PUT /api/auth/profile/update/` - Update user profile

### Tenant Management
- `GET /api/auth/tenants/` - List all tenants
- `POST /api/auth/tenants/` - Create new tenant
- `GET /api/auth/tenant/users/` - Get users for current tenant
- `POST /api/auth/tenant/users/create/` - Create user within tenant

### History & Logging
- `GET /api/auth/history/` - Get API request history
- `GET /api/auth/history/<uuid>/` - Get specific history record
- `GET /api/auth/history/statistics/` - Get usage statistics

### Testing
- `GET /api/auth/test/` - Test endpoint for connectivity

## 💡 Usage Examples

### Register a New Tenant
```bash
curl -X POST http://localhost:8000/api/auth/register/ \
  -H "Content-Type: application/json" \
  -d '{
    "username": "john_doe",
    "email": "john@example.com",
    "password": "securepassword123",
    "password_confirm": "securepassword123",
    "tenant_name": "Acme Corp",
    "first_name": "John",
    "last_name": "Doe"
  }'
```

### User Login
```bash
curl -X POST http://localhost:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{
    "username": "john_doe",
    "password": "securepassword123"
  }'
```

### Access Protected Endpoints
```bash
curl -X GET http://localhost:8000/api/auth/profile/ \
  -H "Authorization: Token YOUR_TOKEN_HERE"
```

### Create Tenant User
```bash
curl -X POST http://localhost:8000/api/auth/tenant/users/create/ \
  -H "Authorization: Token YOUR_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "jane_smith",
    "email": "jane@acme.com",
    "password": "password123",
    "first_name": "Jane",
    "last_name": "Smith"
  }'
```

## 🔧 Management Commands

The project includes several custom management commands for tenant management:

```bash
# Create Token table in a specific tenant DB
python manage.py create_token_table <TENANT_NAME>

# Run migrations for a specific tenant (will connect and migrate that DB)
python manage.py migrate_tenant <TENANT_NAME> [--create]

# Apply only leads app migrations
python manage.py migrate_leads --tenant-name <TENANT_NAME>
python manage.py migrate_leads --all-tenants [--makemigrations]

# Ensure tenant DB has all required tables and safe FK/columns
python manage.py setup_tenant_tables --all-tenants
python manage.py setup_tenant_tables --tenant-id <TENANT_ID>
python manage.py setup_tenant_tables --database-name crm_tenant_<tenant>
python manage.py setup_tenant_tables --fix-foreign-keys

# Migrate Django authtoken tables to tenant DB
python manage.py migrate_authtoken_to_tenant <TENANT_NAME>

# Fix missing/broken auth tables inside tenant DB(s)
python manage.py fix_tenant_auth <TENANT_NAME>
python manage.py fix_tenant_auth <TENANT_NAME> --all

# Migrate existing users into tenant DB (data copy)
python manage.py migrate_users_to_tenant <TENANT_NAME>

# Copy a single user into tenant DB (testing)
python manage.py copy_user_to_tenant <USERNAME> <TENANT_NAME>

# Recreate a tenant database from scratch (DANGER: drops DB)
python manage.py recreate_tenant_db <TENANT_NAME>
```

## 🏢 Multi-Tenancy Implementation

### Tenant Identification
- **Subdomain**: `tenant.localhost:8000`
- **Header**: `X-Tenant: tenant_name`
- **URL Parameter**: `?tenant=tenant_name`

### Database Routing
- Automatic database selection based on tenant context
- Complete data isolation between tenants
- Dynamic database creation for new tenants

### Security Features
- Token-based authentication
- Database-level isolation
- Tenant-specific data routing
- Secure password handling
- API request logging and monitoring

## 📊 Monitoring & Logging

### History Model Features
- **Request Tracking**: All API calls are logged
- **Performance Monitoring**: Execution time tracking
- **Error Logging**: Comprehensive error message capture
- **User Activity**: User and tenant context tracking
- **IP Tracking**: Client IP address logging
- **User Agent**: Browser/client information

### Statistics Available
- API usage statistics
- Error rate monitoring
- Performance metrics
- User activity patterns

## 🛡️ Security Considerations

- **Authentication**: Token-based with automatic expiration
- **Authorization**: Role-based access control
- **Data Isolation**: Complete tenant separation
- **Input Validation**: Comprehensive request validation
- **SQL Injection Protection**: Parameterized queries
- **CORS Configuration**: Configurable cross-origin policies

## 🧪 Testing

### Using Swagger UI
1. Navigate to `http://localhost:8000/swagger/`
2. Click "Authorize" and enter your token
3. Test all endpoints interactively
4. View detailed API documentation

### Manual Testing
```bash
# Test connectivity
curl http://localhost:8000/api/auth/test/

# Test authentication
curl -X POST http://localhost:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"username": "test", "password": "test"}'
```

## 📁 Project Structure

```
crm_saas/
├── crm_saas/           # Main Django project
│   ├── settings.py     # Project settings
│   ├── urls.py         # Main URL configuration
│   └── wsgi.py         # WSGI configuration
├── user/               # User app
│   ├── models.py       # Database models
│   ├── views.py        # API views
│   ├── serializers.py  # Data serializers
│   ├── urls.py         # App URL patterns
│   ├── admin.py        # Admin configuration
│   ├── middleware.py   # Custom middleware
│   ├── authentication.py # Custom authentication
│   ├── database_service.py # Database operations
│   └── management/     # Custom commands
├── requirements.txt    # Python dependencies
├── manage.py          # Django management script
└── README.md          # This file
```

## 🔄 Development Workflow

1. **Feature Development**: Create new features in the `user` app
2. **Database Changes**: Create migrations for model changes
3. **API Testing**: Use Swagger UI for interactive testing
4. **Tenant Testing**: Test multi-tenant functionality
5. **Deployment**: Configure production settings

## 🚀 Deployment

### Production Considerations
- Update `SECRET_KEY` in settings
- Configure production database
- Set `DEBUG = False`
- Configure `ALLOWED_HOSTS`
- Set up proper CORS policies
- Configure static file serving
- Set up SSL certificates

### Environment Variables
```bash
export SECRET_KEY="your-secret-key"
export DEBUG=False
export DATABASE_URL="mysql://user:pass@host:port/db"
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📄 License

This project is licensed under the BSD License - see the LICENSE file for details.

## 🆘 Support

For support and questions:
- Create an issue in the repository
- Check the API documentation at `/swagger/`
- Review the Django admin panel at `/admin/`

## 🔮 Future Enhancements

- [ ] Real-time notifications
- [ ] Advanced analytics dashboard
- [ ] File upload capabilities
- [ ] Email integration
- [ ] Advanced reporting features
- [ ] Mobile API support
- [ ] Webhook integrations
- [ ] Advanced caching strategies

---

**Built with Django 4.2.25 and Django REST Framework 3.16.1**