#!/usr/bin/env python
"""
Backup script to export Twilio configuration before migrating to ClickSend
Run this with: python manage.py shell < backup_twilio_data.py
"""

import json
from datetime import datetime
from core.models import School

def backup_twilio_data():
    """Export all Twilio configurations to a JSON file for backup"""
    
    schools_data = []
    
    for school in School.objects.all():
        school_data = {
            'id': school.id,
            'name': school.name,
            'twilio_account_sid': school.twilio_account_sid,
            'twilio_auth_token': school.twilio_auth_token,
            'twilio_phone_number': school.twilio_phone_number,
            'created_at': school.created_at.isoformat() if school.created_at else None
        }
        schools_data.append(school_data)
    
    backup_data = {
        'backup_date': datetime.now().isoformat(),
        'total_schools': len(schools_data),
        'schools': schools_data
    }
    
    # Save to JSON file
    filename = f"twilio_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, 'w') as f:
        json.dump(backup_data, f, indent=2)
    
    print(f"✅ Twilio data backed up to {filename}")
    print(f"📊 Backed up {len(schools_data)} schools")
    
    return filename

if __name__ == "__main__":
    backup_twilio_data()