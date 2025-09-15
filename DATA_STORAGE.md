
# Pamoja Agencies SHG - Data Storage Information

## Where Your Data is Stored

### Local Development (Current Setup)
Your Pamoja Agencies SHG application data is currently stored in:

1. **Database**: SQLite database file (`pamoja.db`) in your Replit workspace
   - All member information, contributions, loans, fines, and transactions
   - Meeting records, announcements, and documents metadata
   - User authentication and activity logs

2. **File Uploads**: `static/uploads/` directory
   - Document files (PDFs, images, etc.)
   - Logo files and other assets
   - Generated reports

### Production Deployment Options
When you deploy your application, you can choose:

1. **Replit Database**: PostgreSQL hosted by Replit
   - Automatic backups and scaling
   - Secure and reliable
   - Integrated with your Replit deployment

2. **File Storage**: Files stored in your Replit deployment
   - Persistent storage for uploaded documents
   - Automatic backup with deployment

### Data Security
- All passwords are hashed using Werkzeug security
- CSRF protection on all forms
- Role-based access control
- Activity logging for audit trails

### Data Privacy
- Each Replit deployment has its own isolated database
- No data sharing between different instances
- Private and secure by default

### Backup Recommendations
1. Regular exports of financial reports (PDF/CSV)
2. Database backups (handled automatically in production)
3. Document file backups

### Outside Replit Usage
If you want to use this system outside Replit:
1. Export your data using the built-in report generation
2. Set up a new instance with PostgreSQL or MySQL
3. Configure environment variables for production deployment

The application is designed to be portable and can run on any server that supports Flask applications.
